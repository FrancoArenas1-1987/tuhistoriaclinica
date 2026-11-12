import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.db import SessionLocal
from app.models import MedicalOrder, Patient, User
from app.services.medical_images import MAX_UPLOAD_BYTES


def photo_bytes(kind="JPEG", color="white", orientation=None):
    image=Image.new("RGB",(1200,1600),color)
    draw=ImageDraw.Draw(image)
    for n in range(12):draw.text((80,100+n*70),"ORDEN MEDICA - PRUEBA DE LEGIBILIDAD",fill="black",font_size=30)
    out=BytesIO()
    options={}
    if orientation:
        exif=Image.Exif();exif[274]=orientation;exif[270]="PRIVATE METADATA";options["exif"]=exif
    image.save(out,format=kind,**options)
    image.close()
    return out.getvalue()

class MedicalOrdersTest(unittest.TestCase):
    def test_private_photos_lifecycle_and_validation(self):
        ids=[];a=TestClient(app);b=TestClient(app);public=TestClient(app)
        def check(response,code):
            self.assertEqual(response.status_code,code,response.text[:500])
            return response.json() if code!=204 else None
        with TemporaryDirectory() as folder,patch.object(settings,"storage_dir",Path(folder)):
            try:
                for client in (a,b):
                    user=check(client.post("/api/auth/register",json={"full_name":"Prueba Documentos","email":f"orders-{uuid4().hex}@example.com","password":"TestOnly!12345","specialty":"Kinesiología"}),201)
                    ids.append(user["id"])
                patient=check(a.post("/api/patients",json={"rut":"12345678-5","first_names":"Paciente Prueba","last_names":"Documentos","age":30,"first_visit_date":"2026-11-12","pre_existing_conditions":"Sin antecedentes conocidos"}),201)
                pid=patient["id"];url=f"/api/patients/{pid}/medical-orders"
                payload=photo_bytes(orientation=6)
                check(public.get(url),401)
                check(b.post(url,data={"title":"No permitido"},files={"photo":("photo.jpg",payload,"image/jpeg")}),404)
                check(a.post(url,data={"title":"Orden"},files={"photo":("photo.jpg",b"", "image/jpeg")}),422)
                check(a.post(url,data={"title":"Orden"},files={"photo":("photo.jpg",b"<svg onload=alert(1)></svg>","image/jpeg")}),422)
                check(a.post(url,data={"title":"Orden"},files={"photo":("photo.jpg",b"x"*(MAX_UPLOAD_BYTES+1),"image/jpeg")}),413)
                order=check(a.post(url,data={"title":"Orden de kinesiología","document_date":"2026-11-10","notes":"Documento temporal"},files={"photo":("../../private.jpg",payload,"image/jpeg")}),201)
                self.assertEqual((order["width"],order["height"]),(1600,1200))
                self.assertNotIn("storage_key",order)
                oid=order["id"];image_url=f"/api/medical-orders/{oid}/image"
                image_response=a.get(image_url)
                self.assertEqual(image_response.status_code,200)
                self.assertEqual(image_response.headers["content-type"],"image/webp")
                self.assertIn("no-store",image_response.headers["cache-control"])
                with Image.open(BytesIO(image_response.content)) as decoded:
                    self.assertEqual(decoded.format,"WEBP")
                    self.assertEqual(dict(decoded.getexif()),{})
                    self.assertNotIn("xmp",decoded.info)
                thumb=a.get(image_url,params={"thumbnail":"true"})
                self.assertEqual(thumb.status_code,200)
                with Image.open(BytesIO(thumb.content)) as decoded:self.assertLessEqual(max(decoded.size),460)
                self.assertIn("attachment",a.get(image_url,params={"download":"true"}).headers["content-disposition"])
                check(public.get(image_url),401);check(b.get(image_url),404);check(b.get(image_url,params={"thumbnail":"true"}),404)
                check(b.get(url),404);check(b.delete(f"/api/medical-orders/{oid}"),404)
                check(a.post(url,data={"title":"Duplicada"},files={"photo":("same.jpg",payload,"image/jpeg")}),409)
                self.assertEqual(len(check(a.get(url),200)),1)
                self.assertEqual(len(list(Path(folder).rglob("*.webp"))),2)
                with patch.object(settings,"medical_order_quota_mb",0):
                    check(a.post(url,data={"title":"Sin espacio"},files={"photo":("green.jpg",photo_bytes(color="green"),"image/jpeg")}),413)
                # Actual HEIC encoding/decoding, not a renamed JPEG.
                heic=photo_bytes(kind="HEIF")
                heic_order=check(a.post(url,data={"title":"Foto iPhone"},files={"photo":("iphone.heic",heic,"image/heic")}),201)
                self.assertGreater(heic_order["size_bytes"],0)
                check(a.delete(f"/api/medical-orders/{heic_order['id']}"),204)
                check(a.delete(f"/api/medical-orders/{oid}"),204)
                check(a.get(image_url),404)
                self.assertEqual(check(a.get(url),200),[])
                self.assertEqual(list(Path(folder).rglob("*.webp")),[])
                print("Orders: JPEG/HEIC, orientation, metadata stripping, thumbnails, private access, duplicates, quota and deletion OK.")
            finally:
                for client in (a,b,public):client.close()
                if ids:
                    with SessionLocal() as db:
                        db.query(MedicalOrder).filter(MedicalOrder.professional_id.in_(ids)).delete(synchronize_session=False)
                        db.query(Patient).filter(Patient.professional_id.in_(ids)).delete(synchronize_session=False)
                        db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
                        db.commit()

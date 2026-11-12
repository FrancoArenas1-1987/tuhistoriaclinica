from datetime import date
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import logging
import os
import shutil
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db import get_db
from app.services.abuse import check_quota
from app.deps import get_current_user
from app.models import MedicalOrder, User
from app.routers.clinic import own_patient
from app.schemas import MedicalOrderRead
from app.services.medical_images import MAX_UPLOAD_BYTES, optimize_photo, private_path

router = APIRouter(prefix="/api", tags=["Órdenes médicas privadas"])
logger = logging.getLogger(__name__)

def storage_root():
    return Path(settings.storage_dir) / "medical-orders"

def owned_order(db, user, order_id):
    order = db.query(MedicalOrder).filter(MedicalOrder.id == order_id, MedicalOrder.professional_id == user.id).first()
    if not order:
        raise HTTPException(404, "Orden médica no encontrada")
    own_patient(db, user, order.patient_id)
    return order

@router.get("/patients/{patient_id}/medical-orders", response_model=list[MedicalOrderRead])
def list_orders(patient_id: int, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    own_patient(db, user, patient_id)
    return db.query(MedicalOrder).filter(MedicalOrder.patient_id == patient_id, MedicalOrder.professional_id == user.id).order_by(MedicalOrder.created_at.desc(), MedicalOrder.id.desc()).offset(offset).limit(limit).all()

@router.post("/patients/{patient_id}/medical-orders", response_model=MedicalOrderRead, status_code=201)
def upload_order(patient_id: int, photo: UploadFile = File(...), title: str = Form(..., min_length=1, max_length=180), document_date: date | None = Form(default=None), notes: str | None = Form(default=None, max_length=1000), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    own_patient(db, user, patient_id)
    if not title.strip():
        raise HTTPException(422, "Escribe un título para identificar la orden")
    photo.file.seek(0, 2)
    original_size = photo.file.tell()
    photo.file.seek(0)
    if original_size > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "La foto supera el límite de 12 MB")
    if not original_size:
        raise HTTPException(422, "Selecciona una foto antes de guardar")
    try:
        image, thumbnail, width, height = optimize_photo(photo.file)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    finally:
        photo.file.close()
    if len(image) > 4 * 1024 * 1024:
        raise HTTPException(422, "La imagen sigue siendo muy pesada. Toma una foto más cercana de la orden.")
    digest = sha256(image).hexdigest()
    # Serialize quota and duplicate checks for this professional.
    db.execute(select(User.id).where(User.id == user.id).with_for_update()).scalar_one()
    check_quota(db, user, MedicalOrder, settings.medical_order_count_quota, "órdenes médicas", already_locked=True)
    if db.query(MedicalOrder.id).filter(MedicalOrder.patient_id == patient_id, MedicalOrder.sha256 == digest).first():
        raise HTTPException(409, "Esta foto ya está guardada en la ficha del paciente")
    used = db.query(func.coalesce(func.sum(MedicalOrder.size_bytes + MedicalOrder.thumbnail_bytes), 0)).filter(MedicalOrder.professional_id == user.id).scalar()
    if used + len(image) + len(thumbnail) > settings.medical_order_quota_mb * 1024 * 1024:
        raise HTTPException(413, "Se alcanzó el espacio disponible para órdenes médicas de esta cuenta")
    root = storage_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if shutil.disk_usage(root).free < len(image) + len(thumbnail) + 50 * 1024 * 1024:
        raise HTTPException(503, "No hay espacio disponible. Intenta nuevamente más tarde.")
    key = f"{user.id}/{uuid4().hex}"
    full_path = private_path(root, key)
    thumb_path = private_path(root, key, True)
    full_path.parent.mkdir(mode=0o700, exist_ok=True)
    created = []
    try:
        for path, content in ((full_path, image), (thumb_path, thumbnail)):
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
        order = MedicalOrder(professional_id=user.id, patient_id=patient_id, title=title.strip(), document_date=document_date, notes=notes.strip() if notes else None,
            storage_key=key, sha256=digest, size_bytes=len(image), thumbnail_bytes=len(thumbnail), original_size_bytes=original_size, width=width, height=height)
        db.add(order)
        db.commit()
    except Exception as exc:
        db.rollback()
        for path in created:
            path.unlink(missing_ok=True)
        if isinstance(exc, IntegrityError):
            raise HTTPException(409, "Esta foto ya está guardada en la ficha del paciente")
        raise
    db.refresh(order)
    return order

@router.get("/medical-orders/{order_id}/image")
def order_image(order_id: int, thumbnail: bool = False, download: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = owned_order(db, user, order_id)
    try:
        path = private_path(storage_root(), order.storage_key, thumbnail)
    except ValueError:
        raise HTTPException(404, "Archivo no encontrado")
    if not path.is_file():
        raise HTTPException(404, "El archivo no está disponible en esta instalación")
    return FileResponse(path, media_type="image/webp", filename=f"orden-medica-{order.id}.webp", content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": "private, no-store", "Vary": "Cookie, Authorization", "X-Content-Type-Options": "nosniff"})

@router.delete("/medical-orders/{order_id}", status_code=204)
def delete_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = owned_order(db, user, order_id)
    paths = [private_path(storage_root(), order.storage_key, flag) for flag in (False, True)]
    db.delete(order)
    db.commit()
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.exception("No se pudo retirar un archivo privado de orden médica")

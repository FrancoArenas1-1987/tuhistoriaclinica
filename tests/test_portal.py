"""Integration checks against the configured PostgreSQL database.
Creates uniquely named test accounts and removes only those accounts' records.
Run: python -m unittest discover -s tests -v
"""
import unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from tests.helpers import test_client as TestClient, register
from sqlalchemy import inspect, text
from app.main import app
from app.db import SessionLocal, engine
from app.models import User, Patient, Visit, Appointment

class PortalIntegrationTest(unittest.TestCase):
    def test_complete_private_consultation(self):
        suffix = uuid4().hex
        emails = [f"qa-{suffix}-{i}@example.com" for i in range(2)]
        password = "TestOnly!Password123"
        clients = [TestClient(app), TestClient(app)]
        def check(response, code):
            self.assertEqual(response.status_code, code, response.text)
            return response.json()
        try:
            with TestClient(app) as public:
                for path in ("/", "/portal", "/registro", "/ingresar", "/health"):
                    self.assertEqual(public.get(path).status_code, 200)
                check(public.get("/api/patients"), 401)
            for i, client in enumerate(clients):
                user = check(register(client, json={"full_name":f"Profesional prueba {i}","email":emails[i],"password":password,"specialty":"Kinesiología", "role":"admin"}), 201)
                self.assertEqual(user["role"],"clinician")
                self.assertNotIn("password_hash",user)
            a,b=clients
            check(register(a,json={"full_name":"Duplicado", "email":emails[0].upper(),"password":password,"specialty":"Medicina"}),409)
            payload={"rut":"12.345.678-5","first_names":"Paciente QA","last_names":"Prueba","age":32,"pre_existing_conditions":"Sin antecedentes conocidos","first_visit_date":"2026-11-01","consent_signed":False}
            patient=check(a.post("/api/patients",json=payload),201)
            pid=patient["id"]
            self.assertEqual(patient["rut"],"12345678-5")
            self.assertFalse(patient["consent_signed"])
            check(a.post("/api/patients",json=payload),409)
            other=check(b.post("/api/patients",json=payload),201)
            self.assertNotEqual(pid,other["id"])
            self.assertEqual(len(check(b.get("/api/patients"),200)),1)
            check(b.get(f"/api/patients/{pid}"),404)
            check(b.put(f"/api/patients/{pid}",json=payload),404)
            check(b.get(f"/api/visits/patient/{pid}"),404)
            changed={**payload,"phone":"+56912345678","allergies":"Sin alergias"}
            check(a.put(f"/api/patients/{pid}",json=changed),200)
            check(a.put(f"/api/patients/{pid}",json={**changed,"age":None}),422)
            check(a.post("/api/patients",json={**payload,"rut":"12345678-1"}),422)
            visit={"patient_id":pid,"visit_date":"2026-11-12","new_findings":"Evolución favorable","pain_scale":0,"treatment_plan":"Continuar tratamiento"}
            v=check(a.post("/api/visits",json=visit),201)
            check(a.post("/api/visits",json={**visit,"visit_date":"2026-11-02"}),201)
            self.assertEqual(check(a.get(f"/api/patients/{pid}"),200)["last_visit_date"],"2026-11-12")
            check(b.post("/api/visits",json=visit),404)
            check(b.put(f"/api/visits/{v['id']}",json=visit),404)
            check(a.put(f"/api/visits/{v['id']}",json={**visit,"visit_date":"2026-11-01"}),200)
            self.assertEqual(check(a.get(f"/api/patients/{pid}"),200)["last_visit_date"],"2026-11-02")
            check(a.put(f"/api/visits/{v['id']}",json={**visit,"new_findings":None}),422)
            appointment={"patient_id":pid,"starts_at":"2026-11-13T09:00:00-03:00","ends_at":"2026-11-13T09:45:00-03:00","reason":"Evaluación"}
            ap=check(a.post("/api/appointments",json=appointment),201)
            check(a.post("/api/appointments",json=appointment),409)
            check(b.post("/api/appointments",json=appointment),404)
            check(b.put(f"/api/appointments/{ap['id']}",json=appointment),404)
            check(a.post("/api/appointments",json={**appointment,"ends_at":"2026-11-13T08:00:00-03:00"}),422)
            check(a.post("/api/appointments",json={**appointment,"starts_at":"2026-11-13T09:00:00"}),422)
            check(a.put(f"/api/appointments/{ap['id']}",json={**appointment,"status":"cancelled"}),200)
            check(a.post("/api/appointments",json=appointment),201)
            params={"start":"2026-11-13T00:00:00-03:00","end":"2026-11-14T00:00:00-03:00"}
            self.assertEqual(len(check(a.get("/api/appointments",params=params),200)),2)
            self.assertEqual(check(b.get("/api/appointments",params=params),200),[])
            # Requests racing to book the same slot must not both succeed.
            race={**appointment,"starts_at":"2026-11-14T09:00:00-03:00","ends_at":"2026-11-14T09:45:00-03:00"}
            def book(_):
                with TestClient(app) as c:
                    check(c.post("/api/auth/login",json={"email":emails[0],"password":password}),200)
                    return c.post("/api/appointments",json=race).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(sorted(pool.map(book,range(2))),[201,409])
            profile={"full_name":"Profesional Actualizado","specialty":"Psicología","phone":"12345678","appointment_minutes":60,"work_start":"08:30","work_end":"17:00"}
            check(a.put("/api/auth/profile",json=profile),200)
            check(a.put("/api/auth/profile",json={**profile,"work_end":"07:00"}),422)
            self.assertEqual(check(a.get("/api/dashboard"),200),{"patients":1,"visits":2})
            check(a.post("/api/auth/logout"),200)
            check(a.get("/api/auth/me"),401)
            check(a.post("/api/auth/login",json={"email":emails[0],"password":"wrong-password"}),401)
            check(a.post("/api/auth/login",json={"email":emails[0],"password":password}),200)
            print("Verified registration, privacy, patients, visits, scheduling, concurrency, profile and login.")
        finally:
            for client in clients:
                client.close()
            with SessionLocal() as db:
                ids=[r.id for r in db.query(User).filter(User.email.in_(emails))]
                if ids:
                    db.query(Appointment).filter(Appointment.professional_id.in_(ids)).delete(synchronize_session=False)
                    db.query(Visit).filter(Visit.professional_id.in_(ids)).delete(synchronize_session=False)
                    db.query(Patient).filter(Patient.professional_id.in_(ids)).delete(synchronize_session=False)
                    db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
                    db.commit()

if __name__ == "__main__":
    unittest.main()

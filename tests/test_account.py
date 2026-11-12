"""Credential and profile integration checks with disposable accounts only."""
import unittest
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import User

class AccountTest(unittest.TestCase):
    def test_profile_password_and_session_revocation(self):
        suffix=uuid4().hex
        email=f"account-{suffix}@example.com"
        email2=f"other-{suffix}@example.com"
        new_email=f"changed-{suffix}@example.com"
        password="OriginalTestOnly!123"
        new_password="NewTestOnly!12345"
        ids=[]
        clients=[TestClient(app) for _ in range(3)]
        a,b,other=clients
        def check(response,status):
            self.assertEqual(response.status_code,status,response.text)
            return response.json()
        try:
            with TestClient(app) as public:
                check(public.put("/api/auth/password",json={"current_password":password,"new_password":new_password,"confirm_password":new_password}),401)
            for client,mail in ((a,email),(other,email2)):
                user=check(client.post("/api/auth/register",json={"full_name":"Prueba Cuenta","specialty":"Kinesiología","email":mail,"password":password}),201)
                ids.append(user["id"])
                self.assertNotIn("session_version",user)
            check(b.post("/api/auth/login",json={"email":email,"password":password}),200)
            profile={"full_name":"Perfil Editado","specialty":"Piso Pélvico","phone":"+56912345678","appointment_minutes":60,"work_start":"08:30","work_end":"18:00"}
            result=check(a.put("/api/auth/profile",json=profile),200)
            self.assertEqual(result["full_name"],"Perfil Editado")
            self.assertEqual(result["phone"],profile["phone"])
            check(a.put("/api/auth/profile",json={**profile,"email":new_email}),400)
            check(a.put("/api/auth/profile",json={**profile,"email":new_email,"current_password":"wrong-password"}),400)
            check(a.put("/api/auth/profile",json={**profile,"full_name":"No guardar","email":email2,"current_password":password}),409)
            self.assertEqual(check(a.get("/api/auth/me"),200)["full_name"],"Perfil Editado")
            result=check(a.put("/api/auth/profile",json={**profile,"email":new_email.upper(),"current_password":password}),200)
            self.assertEqual(result["email"],new_email)
            check(b.get("/api/auth/me"),401)
            check(a.get("/api/auth/me"),200)
            check(b.post("/api/auth/login",json={"email":email,"password":password}),401)
            check(b.post("/api/auth/login",json={"email":new_email,"password":password}),200)
            old_cookie=a.cookies.get("thc_token")
            payload={"current_password":password,"new_password":new_password,"confirm_password":new_password}
            check(a.put("/api/auth/password",json={**payload,"current_password":"wrong-password"}),400)
            check(a.put("/api/auth/password",json={**payload,"confirm_password":"Mismatch123!"}),422)
            check(a.put("/api/auth/password",json={**payload,"new_password":"short","confirm_password":"short"}),422)
            check(a.put("/api/auth/password",json={**payload,"new_password":password,"confirm_password":password}),422)
            check(a.put("/api/auth/password",json={**payload,"new_password":"é"*40,"confirm_password":"é"*40}),422)
            check(b.get("/api/auth/me"),200)
            check(a.put("/api/auth/password",json=payload),200)
            self.assertNotEqual(old_cookie,a.cookies.get("thc_token"))
            check(a.get("/api/auth/me"),200)
            check(b.get("/api/auth/me"),401)
            check(a.get("/api/auth/me",headers={"Authorization":f"Bearer {old_cookie}"}),401)
            check(a.post("/api/auth/login",json={"email":new_email,"password":password}),401)
            check(a.post("/api/auth/login",json={"email":new_email,"password":new_password}),200)
            check(other.post("/api/auth/login",json={"email":email2,"password":password}),200)
            self.assertEqual(check(other.get("/api/auth/me"),200)["email"],email2)
            with SessionLocal() as db:
                stored=db.get(User,ids[0])
                self.assertNotEqual(stored.password_hash,new_password)
                self.assertEqual(stored.session_version,2)
            print("Account: profile, email conflicts, password validation, old login and other-session revocation OK.")
        finally:
            for client in clients:client.close()
            if ids:
                with SessionLocal() as db:
                    db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
                    db.commit()

"""Meaningful abuse, concurrency and regression checks against a disposable DB."""
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4
from fastapi import HTTPException, Request
from jose import jwt
from sqlalchemy import delete
from app.main import app
from app.core.config import settings
from app.db import SessionLocal
from app.models import AbuseState, User, Patient, Visit, Appointment, MedicalOrder
from app.services import abuse
from tests.helpers import test_client, register


class AbuseTest(unittest.TestCase):
    def setUp(self):
        self.clients = []
        self.ids = []
        self.password = "TestOnly!Password123"
        self.payload = {"full_name": "Prueba Seguridad", "specialty": "Medicina",
                        "email": f"abuse-{uuid4().hex}@example.com", "password": self.password}

    def client(self, **kwargs):
        client = test_client(app, **kwargs)
        self.clients.append(client)
        return client

    def track(self, response):
        self.assertEqual(response.status_code, 201, response.text)
        self.ids.append(response.json()["id"])
        return response.json()

    def tearDown(self):
        for client in self.clients:
            client.close()
        with SessionLocal.begin() as db:
            for model in (MedicalOrder, Appointment, Visit, Patient):
                db.query(model).filter(model.professional_id.in_(self.ids)).delete(synchronize_session=False)
            db.query(User).filter(User.id.in_(self.ids)).delete(synchronize_session=False)

    def test_form_trap_timing_replay_binding_expiry_and_normal_registration(self):
        c = self.client()
        self.assertEqual(c.post("/api/auth/register", json=self.payload).status_code, 422)
        def form():
            r = c.get("/api/auth/registration-form")
            self.assertIn("no-store", r.headers["cache-control"])
            self.assertIn("HttpOnly", r.headers["set-cookie"])
            return r.json()["token"]
        token = form()
        issued = jwt.decode(token, settings.secret_key, algorithms=["HS256"])["issued"]
        with patch.object(abuse, "now", return_value=issued):
            self.assertEqual(c.post("/api/auth/register", json={**self.payload, "form_token": token}).status_code, 400)
        time.sleep(settings.registration_min_seconds + .1)
        self.assertEqual(c.post("/api/auth/register", json={**self.payload, "form_token": token}).status_code, 400)
        token = form()
        time.sleep(settings.registration_min_seconds + .1)
        self.assertEqual(c.post("/api/auth/register", json={**self.payload, "form_token": token, "website": "spam"}).status_code, 400)
        outsider = self.client()
        self.assertEqual(outsider.post("/api/auth/register", json={**self.payload, "form_token": token}).status_code, 400)
        outsider.cookies.update(c.cookies)
        self.assertEqual(outsider.post("/api/auth/register", json={**self.payload, "form_token": token}).status_code, 400)
        self.assertEqual(c.post("/api/auth/register", json={**self.payload, "form_token": token + "bad"}).status_code, 400)
        claims = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        claims["exp"] = int(time.time()) - 1
        expired = jwt.encode(claims, settings.secret_key, algorithm="HS256")
        self.assertEqual(c.post("/api/auth/register", json={**self.payload, "form_token": expired}).status_code, 400)
        self.track(register(c, json=self.payload))
        self.assertEqual(c.get("/api/auth/me").status_code, 200)
        token = form()
        time.sleep(settings.registration_min_seconds + .1)
        def submit(_):
            return c.post("/api/auth/register", json={**self.payload, "email": f"nonce-{uuid4().hex}@example.com", "form_token": token})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(submit, range(2)))
        self.assertEqual(sorted(r.status_code for r in responses), [201, 400])
        self.track(next(r for r in responses if r.status_code == 201))
        fresh = form()
        issued = jwt.decode(fresh, settings.secret_key, algorithms=["HS256"])["issued"]
        with patch.object(abuse, "now", return_value=issued):
            self.assertEqual(c.post("/api/auth/register", json={**self.payload, "form_token": fresh}).status_code, 400)

    def test_concurrent_counter_and_process_restart(self):
        identity = uuid4().hex
        rule = [("qa-limit", identity, 3, 60)]
        def attempt(_):
            try:
                abuse.enforce_limits(rule)
                return 200
            except HTTPException as exc:
                return exc.status_code
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(attempt, range(12)))
        self.assertEqual(results.count(200), 3)
        self.assertEqual(results.count(429), 9)
        script = f"from app.services.abuse import enforce_limits; enforce_limits({rule!r})"
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("429", result.stderr)
        with patch.object(abuse, "now", return_value=abuse.now() + 61):
            abuse.enforce_limits(rule)

    def test_registration_limit_per_ip_and_forwarded_headers_ignored(self):
        c = self.client()
        with patch.object(settings, "registration_hour_limit", 1):
            self.track(register(c, json=self.payload))
            c.headers["X-Forwarded-For"] = "203.0.113.90"
            c.headers["X-Real-IP"] = "203.0.113.91"
            response = register(c, json={**self.payload, "email": f"blocked-{uuid4().hex}@example.com"})
            self.assertEqual(response.status_code, 429, response.text)
            self.assertGreater(int(response.headers["retry-after"]), 0)
            self.assertEqual(c.get("/api/auth/me").status_code, 200)
        other = self.client()
        self.track(register(other, json={**self.payload, "email": f"other-{uuid4().hex}@example.com"}))

    def test_progressive_login_delays_reset_and_other_network(self):
        c = self.client()
        self.track(register(c, json=self.payload))
        login = {"email": self.payload["email"], "password": "wrong-password"}
        timestamp = abuse.now()
        with patch.object(abuse, "now", return_value=timestamp):
            for status in (401, 401, 429):
                self.assertEqual(c.post("/api/auth/login", json=login).status_code, status)
            good = {**login, "password": self.password}
            response = c.post("/api/auth/login", json=good)
            self.assertEqual(response.status_code, 429)
            self.assertIn("retry-after", response.headers)
            other = self.client()
            self.assertEqual(other.post("/api/auth/login", json=good).status_code, 200)
        with patch.object(abuse, "now", return_value=timestamp + 4):
            self.assertEqual(c.post("/api/auth/login", json=good).status_code, 200)
            self.assertEqual(c.post("/api/auth/login", json=login).status_code, 401)
        for _ in range(40):
            try:
                abuse.enforce_limits([("login-account", "unknown@example.com", 40, 900)])
            except HTTPException:
                self.fail("Account budget exhausted prematurely")
        with self.assertRaises(HTTPException):
            abuse.enforce_limits([("login-account", "unknown@example.com", 40, 900)])

    def test_body_origin_ipv6_and_clinical_quotas(self):
        c = self.client()
        self.assertEqual(c.post("/api/auth/login", json={"email": self.payload["email"], "password": "x" * 20000}).status_code, 413)
        self.assertEqual(c.post("/api/auth/login", content=iter([b"x" * 17000])).status_code, 413)
        invalid = c.post("/api/auth/login", json={"email": "invalid", "password": "PrivateSentinel123!"})
        self.assertEqual(invalid.status_code, 422)
        self.assertNotIn("PrivateSentinel123!", invalid.text)
        self.assertEqual(c.get("/api/auth/registration-form", headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403)
        self.assertEqual(c.post("/api/auth/register", json=self.payload, headers={"Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(c.post("/api/auth/register", json=self.payload, headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403)
        request = lambda ip: Request({"type": "http", "client": (ip, 123), "headers": []})
        self.assertEqual(abuse.client_identity(request("2001:db8:1234:5678::1")), abuse.client_identity(request("2001:db8:1234:5678::999")))
        self.track(register(c, json=self.payload))
        patient = {"rut": "12345678-5", "first_names": "Paciente", "last_names": "Prueba", "age": 30,
                   "pre_existing_conditions": "Sin antecedentes", "first_visit_date": "2026-11-12"}
        with patch.object(settings, "patient_quota", 1):
            response = c.post("/api/patients", json=patient)
            self.assertEqual(response.status_code, 201, response.text)
            pid = response.json()["id"]
            self.assertEqual(c.post("/api/patients", json=patient).status_code, 409)
            self.assertEqual(c.put(f"/api/patients/{pid}", json=patient).status_code, 200)
        visit = {"patient_id": pid, "visit_date": "2026-11-12", "new_findings": "Prueba"}
        with patch.object(settings, "visit_quota", 0):
            self.assertEqual(c.post("/api/visits", json=visit).status_code, 409)
        appointment = {"patient_id": pid, "starts_at": "2026-11-13T09:00:00-03:00", "ends_at": "2026-11-13T09:45:00-03:00"}
        with patch.object(settings, "appointment_quota", 0):
            self.assertEqual(c.post("/api/appointments", json=appointment).status_code, 409)
        self.assertEqual(c.put(f"/api/patients/{pid}", json={**patient, "medications": "x" * 66000}).status_code, 413)
        self.assertEqual(c.get(f"/api/patients/{pid}").status_code, 200)
        with SessionLocal.begin() as db:
            row = db.get(AbuseState, abuse.state_key("user-write", str(self.ids[0])))
            row.count = 120
        response = c.put(f"/api/patients/{pid}", json=patient)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(c.get(f"/api/patients/{pid}").status_code, 200)

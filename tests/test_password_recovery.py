"""Password recovery with fake SMTP only; never sends real email."""
import secrets
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4
from pydantic import SecretStr
from app.main import app
from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.db import SessionLocal
from app.models import User, PasswordReset
from app.services import abuse, password_recovery as recovery
from tests.helpers import test_client, register


class FakeSMTP:
    sent = []
    calls = []
    def __init__(self,*args,**kwargs): self.calls.append("connect")
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def ehlo(self): self.calls.append("ehlo")
    def starttls(self,context):
        assert context.check_hostname
        self.calls.append("tls")
    def login(self,*args): self.calls.append("login")
    def send_message(self,message):
        self.calls.append("send")
        self.sent.append(message)


class PasswordRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.ids=[];self.clients=[]
        self.password="OriginalTestOnly!123"
        self.email=f"recovery-{uuid4().hex}@example.com"
        FakeSMTP.sent=[];FakeSMTP.calls=[]
        self.config=patch.multiple(settings,password_recovery_enabled=True,public_base_url="https://clinic.example.com",smtp_host="smtp.invalid",
            smtp_port=587,smtp_security="starttls",smtp_username="sender@example.com",
            smtp_password=SecretStr("test-only-not-a-real-secret"),smtp_from="sender@example.com")
        self.config.start()
        self.mail=patch.object(recovery.smtplib,"SMTP",FakeSMTP);self.mail.start()
        self.c=self.client()
        response=register(self.c,json={"email":self.email,"password":self.password,"full_name":"Prueba Recuperación","specialty":"Medicina"})
        self.assertEqual(response.status_code,201,response.text)
        self.uid=response.json()["id"];self.ids.append(self.uid)

    def client(self):
        client=test_client(app);self.clients.append(client);return client

    def tearDown(self):
        self.mail.stop();self.config.stop()
        for client in self.clients:client.close()
        with SessionLocal.begin() as db:
            db.query(User).filter(User.id.in_(self.ids)).delete(synchronize_session=False)

    def forgot(self,client=None,email=None,**kwargs):
        return (client or self.c).post("/api/auth/forgot-password",json={"email":email or self.email},**kwargs)

    def token(self):
        text=FakeSMTP.sent[-1].get_content()
        return text.split("#token=",1)[1].split()[0]

    def payload(self,token=None):
        return {"token":token or self.token(),"new_password":"ReplacementOnly!1234","confirm_password":"ReplacementOnly!1234"}

    def test_complete_recovery_privacy_and_sessions(self):
        other=self.client()
        self.assertEqual(other.post("/api/auth/login",json={"email":self.email,"password":self.password}).status_code,200)
        old=self.c.cookies.get("thc_token")
        response=self.forgot(headers={"Host":"untrusted.example"})
        self.assertEqual(response.status_code,202,response.text)
        unknown=self.forgot(email=f"unknown-{uuid4().hex}@example.com")
        self.assertEqual(response.json(),unknown.json())
        self.assertEqual(unknown.status_code,202)
        self.assertEqual(len(FakeSMTP.sent),1)
        token=self.token();message=FakeSMTP.sent[0]
        self.assertNotIn(token,response.text)
        self.assertNotIn(token,message["Subject"])
        self.assertIn("https://clinic.example.com/restablecer-contrasena#token=",message.get_content())
        self.assertNotIn("untrusted.example",message.get_content())
        self.assertEqual(FakeSMTP.calls,["connect","ehlo","tls","ehlo","login","send"])
        with SessionLocal() as db:
            row=db.get(PasswordReset,self.uid)
            self.assertEqual(row.token_hash,recovery.token_digest(token))
            self.assertNotEqual(row.token_hash,token)
            self.assertEqual(row.session_version,0)
        self.assertEqual(self.c.get("/api/auth/me").status_code,200)
        payload=self.payload()
        self.assertEqual(other.post("/api/auth/reset-password",json={**payload,"confirm_password":"Mismatch123!"}).status_code,422)
        same={"token":token,"new_password":self.password,"confirm_password":self.password}
        self.assertEqual(other.post("/api/auth/reset-password",json=same).status_code,400)
        for password in ("short","é"*40):
            self.assertEqual(other.post("/api/auth/reset-password",json={"token":token,"new_password":password,"confirm_password":password}).status_code,422)
        result=self.c.post("/api/auth/reset-password",json=payload)
        self.assertEqual(result.status_code,200,result.text)
        self.assertIn("no-store",result.headers["cache-control"])
        self.assertEqual(self.c.get("/api/auth/me").status_code,401)
        self.assertEqual(other.get("/api/auth/me").status_code,401)
        self.assertEqual(other.get("/api/auth/me",headers={"Authorization":"Bearer "+old}).status_code,401)
        self.assertEqual(other.post("/api/auth/reset-password",json=payload).status_code,400)
        self.assertEqual(self.c.post("/api/auth/login",json={"email":self.email,"password":self.password}).status_code,401)
        self.assertEqual(self.c.post("/api/auth/login",json={"email":self.email,"password":payload["new_password"]}).status_code,200)
        with SessionLocal() as db:
            self.assertIsNone(db.get(PasswordReset,self.uid))
            self.assertEqual(db.get(User,self.uid).session_version,1)
            self.assertNotEqual(db.get(User,self.uid).password_hash,payload["new_password"])

    def test_expiry_revocation_reissue_and_concurrency(self):
        self.assertEqual(self.forgot().status_code,202)
        original=self.token()
        # Repeated requests inside the cooldown do not replace the link or send more email.
        self.assertEqual(self.forgot().status_code,202)
        self.assertEqual(len(FakeSMTP.sent),1)
        self.assertEqual(self.c.post("/api/auth/reset-password",json=self.payload(secrets.token_urlsafe(32))).status_code,400)
        with SessionLocal.begin() as db:db.get(PasswordReset,self.uid).expires_at=recovery.now()-1
        self.assertEqual(self.c.post("/api/auth/reset-password",json=self.payload(original)).status_code,400)
        timestamp=recovery.now()+61
        with patch.object(abuse,"now",return_value=timestamp),patch.object(recovery,"now",return_value=timestamp):
            self.assertEqual(self.forgot().status_code,202)
        self.assertEqual(len(FakeSMTP.sent),2)
        fresh=self.token();self.assertNotEqual(fresh,original)
        self.assertEqual(self.c.post("/api/auth/reset-password",json=self.payload(original)).status_code,400)
        a,b=self.client(),self.client()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda c:c.post("/api/auth/reset-password",json=self.payload(fresh)).status_code,(a,b)))
        self.assertEqual(sorted(results),[200,400])

    def test_token_invalid_after_account_changes_or_suspension(self):
        self.assertEqual(self.forgot().status_code,202)
        token=self.token()
        with SessionLocal.begin() as db:
            user=db.get(User,self.uid);user.session_version+=1
        self.assertEqual(self.c.post("/api/auth/reset-password",json=self.payload(token)).status_code,400)
        with SessionLocal.begin() as db:
            user=db.get(User,self.uid);user.session_version=0;user.is_active=False
        self.assertEqual(self.c.post("/api/auth/reset-password",json=self.payload(token)).status_code,400)

    def test_unconfigured_failure_tls_ssl_and_request_limits(self):
        with patch.object(settings,"smtp_password",None):
            response=self.forgot();self.assertEqual(response.status_code,503)
            self.assertEqual(self.forgot(email="unknown@example.com").json(),response.json())
        with patch.object(recovery.smtplib,"SMTP",side_effect=OSError("PrivateSMTPDetails")):
            with self.assertLogs(recovery.logger,level="ERROR") as logs:
                self.assertEqual(self.forgot().status_code,202)
            self.assertNotIn("PrivateSMTPDetails",str(logs.output))
        with SessionLocal() as db:self.assertIsNone(db.get(PasswordReset,self.uid))
        with patch.object(settings,"smtp_security","ssl"),patch.object(recovery.smtplib,"SMTP_SSL",FakeSMTP):
            recovery.send_email(self.email,secrets.token_urlsafe(32))
        limited_client=self.client()
        for _ in range(10):self.assertEqual(self.forgot(limited_client,email="unknown@example.com").status_code,202)
        response=self.forgot(limited_client,email="unknown@example.com")
        self.assertEqual(response.status_code,429)
        self.assertIn("retry-after",response.headers)
        self.assertEqual(self.c.post("/api/auth/reset-password",json=self.payload("a"*43),headers={"Origin":"https://evil.example"}).status_code,403)

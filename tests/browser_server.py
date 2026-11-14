"""Local-only browser QA app. No real email and no test endpoints in production."""
import json
import os
from pathlib import Path
from pydantic import SecretStr

mailbox = os.environ.get("QA_MAILBOX_FILE")
if not mailbox:
    raise RuntimeError("Use only through tests.run_isolated --browser")
from app.main import app
from app.core.config import settings
from app.services import password_recovery
settings.password_recovery_enabled = True
settings.public_base_url = "http://127.0.0.1:8001"
settings.smtp_host = "smtp.invalid"
settings.smtp_username = "qa@example.com"
settings.smtp_password = SecretStr("test-only")
settings.smtp_from = "qa@example.com"


def capture(recipient, token):
    Path(mailbox).write_text(json.dumps({"recipient": recipient, "token": token}), encoding="utf-8")
password_recovery.send_email = capture

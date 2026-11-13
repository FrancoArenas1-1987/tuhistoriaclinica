"""Opaque one-use email recovery; no plaintext tokens in the database or logs."""
import hashlib
import logging
import secrets
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from urllib.parse import urlsplit
from fastapi import HTTPException
from sqlalchemy import delete, select
from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.db import SessionLocal
from app.models import PasswordReset, User
from app.services.abuse import enforce_limits, now

logger = logging.getLogger(__name__)
GENERIC_MESSAGE = "Si el correo está asociado a una cuenta, recibirás instrucciones para crear una nueva contraseña. Revisa también la carpeta de spam."
INVALID_MESSAGE = "El enlace no es válido o ya venció. Solicita uno nuevo."


def mail_ready():
    try:
        base = urlsplit(settings.public_base_url or "")
        safe_base = (base.scheme == "https" or base.scheme == "http" and settings.environment != "prod"
                     and base.hostname in ("localhost", "127.0.0.1"))
        return bool(safe_base and base.hostname and not base.username and not base.password
                    and not base.query and not base.fragment and base.path in ("", "/")
                    and settings.smtp_host and settings.smtp_from and settings.smtp_username
                    and settings.smtp_password and settings.smtp_password.get_secret_value())
    except ValueError:
        return False


def token_digest(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def send_email(recipient, token):
    message = EmailMessage()
    message["Subject"] = "Recupera tu acceso a TuHistoriaClinica"
    message["From"] = formataddr(("TuHistoriaClinica", str(settings.smtp_from)))
    message["To"] = recipient
    link = settings.public_base_url.rstrip("/") + "/restablecer-contrasena#token=" + token
    message.set_content(f"Solicitaste crear una nueva contraseña para tu cuenta.\n\nAbre este enlace:\n{link}\n\nEl enlace vence en {settings.password_reset_minutes} minutos y funciona una sola vez.\nSi no hiciste esta solicitud, ignora este correo. Tu contraseña no ha cambiado.\n\nTuHistoriaClinica")
    context = ssl.create_default_context()
    if settings.smtp_security == "ssl":
        connection = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15, context=context)
    else:
        connection = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
    with connection as smtp:
        if settings.smtp_security == "starttls":
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
        smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)


def _deliver_recovery(email):
    # Runs after the generic HTTP response is sent, hiding account lookup and SMTP timing.
    if not mail_ready():
        return
    try:
        enforce_limits([("reset-email", email, 3, 3600), ("reset-cooldown", email, 1, 60)])
    except HTTPException:
        return
    token = secrets.token_urlsafe(32)
    digest = token_digest(token)
    timestamp = now()
    with SessionLocal.begin() as db:
        expired = select(PasswordReset.user_id).where(PasswordReset.expires_at <= timestamp).limit(200)
        db.execute(delete(PasswordReset).where(PasswordReset.user_id.in_(expired)), execution_options={"synchronize_session": False})
    # Finish cleanup before locking users, avoiding the inverse token/user lock order.
    with SessionLocal.begin() as db:
        user = db.query(User).filter(User.email == email, User.is_active.is_(True)).with_for_update().first()
        if not user:
            return
        row = db.get(PasswordReset, user.id)
        if row is None:
            row = PasswordReset(user_id=user.id)
            db.add(row)
        row.token_hash, row.session_version = digest, user.session_version
        row.expires_at = timestamp + settings.password_reset_minutes * 60
    try:
        send_email(email, token)
    except Exception as exc:
        # SMTP errors can contain sensitive server data; never log their message or token.
        logger.error("No se pudo enviar el correo de recuperación (%s)", type(exc).__name__)
        with SessionLocal.begin() as db:
            db.execute(delete(PasswordReset).where(PasswordReset.token_hash == digest))


def reset_password(payload, db):
    digest = token_digest(payload.token)
    uid = db.execute(select(PasswordReset.user_id).where(PasswordReset.token_hash == digest)).scalar_one_or_none()
    if uid is None:
        raise HTTPException(400, INVALID_MESSAGE)
    # Same lock order as issuance/profile changes: user, then recovery token.
    user = db.query(User).filter(User.id == uid).with_for_update().first()
    row = db.query(PasswordReset).filter(PasswordReset.user_id == uid).populate_existing().with_for_update().first()
    if (not user or not user.is_active or not row or row.token_hash != digest
        or row.expires_at <= now() or row.session_version != user.session_version):
        raise HTTPException(400, INVALID_MESSAGE)
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(400, "Elige una contraseña diferente de la anterior.")
    user.password_hash = hash_password(payload.new_password)
    user.session_version += 1
    db.delete(row)
    db.commit()


def deliver_recovery(email):
    try:
        _deliver_recovery(email)
    except Exception as exc:
        logger.error("No se pudo procesar la recuperación de cuenta (%s)", type(exc).__name__)

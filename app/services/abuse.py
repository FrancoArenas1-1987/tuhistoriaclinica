"""Database-backed abuse controls shared across workers and application restarts."""
import hashlib
import hmac
import ipaddress
import math
import secrets
import time
from fastapi import HTTPException
from jose import JWTError, jwt
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.core.config import settings
from app.db import SessionLocal
from app.models import AbuseState, User

FORM_COOKIE = "thc_registration"


def now():
    return int(time.time())


def state_key(scope, identity):
    digest = hmac.new(settings.secret_key.encode(), f"{scope}:{identity}".encode(), hashlib.sha256).hexdigest()
    return f"{scope}:{digest}"


def client_identity(request):
    # Uvicorn's client is only trustworthy behind a proxy which overwrites X-Forwarded-For.
    # Never read a client-supplied X-Real-IP/Forwarded header here.
    host = request.client.host if request.client else "unknown"
    try:
        address = ipaddress.ip_address(host)
        if isinstance(address, ipaddress.IPv6Address):
            if address.ipv4_mapped:
                return str(address.ipv4_mapped)
            return str(ipaddress.ip_network(f"{address}/64", strict=False))
        return str(address)
    except ValueError:
        return host[:200]


def insert_state(db, key, timestamp, expires):
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    return db.execute(insert(AbuseState).values(key=key, count=0, window_start=timestamp,
        blocked_until=0, expires_at=expires).on_conflict_do_nothing(index_elements=["key"]).returning(AbuseState.key))


def cleanup(db, timestamp):
    expired = select(AbuseState.key).where(AbuseState.expires_at <= timestamp).limit(200)
    db.execute(delete(AbuseState).where(AbuseState.key.in_(expired)), execution_options={"synchronize_session": False})


def limited(retry):
    seconds = max(1, math.ceil(retry))
    return HTTPException(429, f"Demasiados intentos. Intenta nuevamente en {seconds} segundos.",
                         headers={"Retry-After": str(seconds), "Cache-Control": "no-store"})


def enforce_limits(rules):
    """Atomically charge all fixed-window budgets, in deterministic lock order."""
    timestamp = now()
    with SessionLocal.begin() as db:
        cleanup(db, timestamp)
        rows = []
        retry = 0
        for scope, identity, limit, seconds in sorted(rules, key=lambda r: state_key(r[0], r[1])):
            key = state_key(scope, identity)
            insert_state(db, key, timestamp, timestamp + seconds)
            row = db.execute(select(AbuseState).where(AbuseState.key == key).with_for_update()).scalar_one()
            if row.expires_at <= timestamp:
                row.count, row.window_start, row.expires_at = 0, timestamp, timestamp + seconds
            if row.count >= limit:
                retry = max(retry, row.expires_at - timestamp)
            rows.append(row)
        if not retry:
            for row in rows:
                row.count += 1
    if retry:
        raise limited(retry)


def request_budget(request):
    ip = client_identity(request)
    path = request.url.path
    if path == "/api/auth/registration-form":
        enforce_limits([("form-ip", ip, 60, 600), ("form-site", "site", 1000, 600)])
    elif path == "/api/auth/register":
        enforce_limits([("reg-attempt", ip, 30, 600)])
    elif path in ("/api/auth/forgot-password", "/api/auth/reset-password"):
        scope = "recover" if path.endswith("forgot-password") else "reset"
        enforce_limits([(scope + "-ip", ip, 10, 900), (scope + "-site", "site", 100, 3600)])
    elif path == "/api/auth/login":
        enforce_limits([("login-ip", ip, 30, 300), ("login-hour", ip, 200, 3600)])


def issue_form(request, response):
    browser = request.cookies.get(FORM_COOKIE, "")
    if len(browser) != 64 or any(c not in "0123456789abcdef" for c in browser):
        browser = secrets.token_hex(32)
    timestamp = now()
    claims = {"purpose": "register", "jti": secrets.token_hex(32), "issued": timestamp,
              "exp": timestamp + settings.registration_token_seconds,
              "binding": state_key("binding", client_identity(request) + ":" + browser)}
    response.set_cookie(FORM_COOKIE, browser, max_age=settings.registration_token_seconds,
                        httponly=True, secure=settings.cookie_secure, samesite="strict", path="/api/auth")
    response.headers["Cache-Control"] = "no-store"
    return {"token": jwt.encode(claims, settings.secret_key, algorithm="HS256"),
            "minimum_seconds": settings.registration_min_seconds,
            "expires_in": settings.registration_token_seconds}


def consume_form(request, payload):
    error = HTTPException(400, "No pudimos validar el formulario. Vuelve a intentarlo.")
    try:
        claims = jwt.decode(payload.form_token, settings.secret_key, algorithms=["HS256"])
        browser = request.cookies.get(FORM_COOKIE, "")
        expected = state_key("binding", client_identity(request) + ":" + browser)
        if (payload.website or not browser or claims.get("purpose") != "register"
            or not isinstance(claims.get("jti"), str) or len(claims["jti"]) != 64
            or not isinstance(claims.get("issued"), int) or not isinstance(claims.get("exp"), int)
            or claims["exp"] <= now() or claims["issued"] > now()
            or not hmac.compare_digest(claims.get("binding", ""), expected)):
            raise error
    except (JWTError, TypeError, ValueError):
        raise error
    # Consume even on a suspiciously fast submission: retries require a fresh form.
    with SessionLocal.begin() as db:
        cleanup(db, now())
        result = insert_state(db, state_key("nonce", claims["jti"]), now(), claims["exp"])
        reused = result.scalar_one_or_none() is None
    if reused or now() - claims["issued"] < settings.registration_min_seconds:
        raise error
    enforce_limits([("reg-hour", client_identity(request), settings.registration_hour_limit, 3600),
                    ("reg-day", client_identity(request), settings.registration_day_limit, 86400),
                    ("reg-site", "site", settings.registration_site_hour_limit, 3600)])


def login_pair(request, email):
    return state_key("login-fail", client_identity(request) + ":" + email.lower())


def check_login(request, email):
    enforce_limits([("login-account", email.lower(), 40, 900)])
    with SessionLocal() as db:
        row = db.get(AbuseState, login_pair(request, email))
        if row and row.expires_at > now() and row.blocked_until > now():
            raise limited(row.blocked_until - now())


def failed_login(request, email):
    timestamp = now()
    key = login_pair(request, email)
    with SessionLocal.begin() as db:
        insert_state(db, key, timestamp, timestamp + 900)
        row = db.execute(select(AbuseState).where(AbuseState.key == key).with_for_update()).scalar_one()
        if row.expires_at <= timestamp:
            row.count = 0
        row.count = min(row.count + 1, 12)
        delay = min(300, 2 ** max(1, row.count - 2)) if row.count >= 3 else 0
        row.blocked_until, row.expires_at = timestamp + delay, timestamp + 900
    if delay:
        raise limited(delay)


def successful_login(request, email):
    with SessionLocal.begin() as db:
        db.execute(delete(AbuseState).where(AbuseState.key == login_pair(request, email)))


def user_budget(request, user):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        rules = [("user-write", str(user.id), 120, 60)]
        if request.method == "POST" and request.url.path.endswith("/medical-orders"):
            rules.append(("user-upload", str(user.id), 10, 60))
        if request.url.path in ("/api/auth/password", "/api/auth/profile"):
            rules.append(("user-security", str(user.id), 20, 300))
        enforce_limits(rules)


def check_quota(db, user, model, limit, label, already_locked=False):
    if not already_locked:
        db.execute(select(User.id).where(User.id == user.id).with_for_update()).scalar_one()
    if db.query(model).filter(model.professional_id == user.id).count() >= limit:
        raise HTTPException(409, f"Se alcanzó el límite de {label} de esta cuenta. Contacta al administrador.")

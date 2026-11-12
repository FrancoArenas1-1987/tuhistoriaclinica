from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.core.security import create_access_token, verify_password, hash_password
from app.deps import get_current_user
from app.db import get_db
from app.models import User, UserRole
from app.schemas import LoginRequest, RegisterRequest, UserRead, ProfileUpdate, PasswordChange

from app.services.abuse import issue_form, consume_form, check_login, failed_login, successful_login

# Equalize password-check work for unknown email addresses.
DUMMY_PASSWORD_HASH = hash_password("dummy-password-not-an-account")

router = APIRouter(prefix="/api/auth", tags=["Cuenta"])

def session_cookie(response, user):
    response.set_cookie("thc_token", create_access_token(str(user.id), user.session_version), httponly=True,
                        samesite="lax", secure=settings.cookie_secure,
                        max_age=settings.access_token_expire_minutes * 60)

@router.get("/registration-form")
def registration_form(request: Request, response: Response):
    return issue_form(request, response)


@router.post("/register", response_model=UserRead, status_code=201)
def register(payload: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    consume_form(request, payload)
    data = payload.model_dump(exclude={"password", "form_token", "website"})
    data["email"] = str(payload.email).lower()
    user = User(**data, role=UserRole.clinician, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Este correo ya está registrado")
    db.refresh(user)
    session_cookie(response, user)
    return user

@router.post("/login", response_model=UserRead)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    check_login(request, str(payload.email))
    user = db.query(User).filter(User.email == str(payload.email).lower(), User.is_active.is_(True)).first()
    valid = len(payload.password.encode("utf-8")) <= 72 and verify_password(payload.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if not user or not valid:
        failed_login(request, str(payload.email))
        raise HTTPException(401, "Correo o contraseña incorrectos")
    successful_login(request, str(payload.email))
    session_cookie(response, user)
    return user

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("thc_token", secure=settings.cookie_secure, httponly=True, samesite="lax")
    return {"ok": True}

@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)):
    return user

@router.put("/profile", response_model=UserRead)
def profile(payload: ProfileUpdate, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user.id).populate_existing().with_for_update().one()
    email = str(payload.email).lower() if payload.email is not None else user.email
    changing_email = email != user.email
    if changing_email:
        if not payload.current_password or len(payload.current_password.encode("utf-8")) > 72 or not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(400, "Para cambiar el correo, ingresa tu contraseña actual correctamente")
    for key, value in payload.model_dump(exclude={"email", "current_password"}).items():
        setattr(user, key, value)
    user.email = email
    if changing_email:
        user.session_version += 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Este correo ya está registrado")
    db.refresh(user)
    if changing_email:
        session_cookie(response, user)
    return user


@router.put("/password")
def change_password(payload: PasswordChange, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user.id).populate_existing().with_for_update().one()
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(400, "La contraseña actual es incorrecta")
    user.password_hash = hash_password(payload.new_password)
    user.session_version += 1
    db.commit()
    db.refresh(user)
    session_cookie(response, user)
    return {"ok": True}

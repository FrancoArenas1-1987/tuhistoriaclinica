from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.db import get_db
from app.deps import get_current_user
from app.models import User, Patient, Visit, Appointment
from app.schemas import PatientCreate, PatientRead, VisitCreate, VisitRead, AppointmentCreate, AppointmentRead

router = APIRouter(prefix="/api", tags=["Consulta privada"])

def own_patient(db, user, patient_id):
    patient = db.query(Patient).filter(Patient.id == patient_id, Patient.professional_id == user.id).first()
    if not patient:
        raise HTTPException(404, "Paciente no encontrado")
    return patient

def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una paciente con ese RUT en tu consulta")

@router.get("/patients", response_model=list[PatientRead])
def patients(q: str = "", offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Patient).filter(Patient.professional_id == user.id)
    if q.strip():
        term = "%" + q.strip() + "%"
        query = query.filter(or_(Patient.first_names.ilike(term), Patient.last_names.ilike(term), Patient.rut.ilike(term)))
    return query.order_by(Patient.updated_at.desc(), Patient.id.desc()).offset(offset).limit(limit).all()

@router.get("/patients/{patient_id}", response_model=PatientRead)
def patient(patient_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return own_patient(db, user, patient_id)

@router.post("/patients", response_model=PatientRead, status_code=201)
def create_patient(payload: PatientCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    patient = Patient(**payload.model_dump(exclude={"last_visit_date"}), professional_id=user.id)
    db.add(patient)
    commit(db)
    db.refresh(patient)
    return patient

@router.put("/patients/{patient_id}", response_model=PatientRead)
def update_patient(patient_id: int, payload: PatientCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    patient = own_patient(db, user, patient_id)
    for key, value in payload.model_dump(exclude={"last_visit_date"}).items():
        setattr(patient, key, value)
    commit(db)
    db.refresh(patient)
    return patient

@router.get("/visits/patient/{patient_id}", response_model=list[VisitRead])
def visits(patient_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    own_patient(db, user, patient_id)
    return db.query(Visit).filter(Visit.patient_id == patient_id, Visit.professional_id == user.id).order_by(Visit.visit_date.desc(), Visit.id.desc()).all()

def save_visit(db, user, payload, visit=None):
    patient = own_patient(db, user, payload.patient_id)
    if visit is None:
        visit = Visit(professional_id=user.id, **payload.model_dump())
        db.add(visit)
    else:
        for key, value in payload.model_dump().items():
            setattr(visit, key, value)
    db.flush()
    patient.last_visit_date = db.query(func.max(Visit.visit_date)).filter(Visit.patient_id == patient.id).scalar()
    db.commit()
    db.refresh(visit)
    return visit

@router.post("/visits", response_model=VisitRead, status_code=201)
def create_visit(payload: VisitCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return save_visit(db, user, payload)

@router.put("/visits/{visit_id}", response_model=VisitRead)
def update_visit(visit_id: int, payload: VisitCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    visit = db.query(Visit).filter(Visit.id == visit_id, Visit.professional_id == user.id).first()
    if not visit:
        raise HTTPException(404, "Atención no encontrada")
    if payload.patient_id != visit.patient_id:
        raise HTTPException(422, "No puedes cambiar el paciente de una atención")
    return save_visit(db, user, payload, visit)

@router.get("/appointments", response_model=list[AppointmentRead])
def appointments(start: datetime, end: datetime, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise HTTPException(422, "Rango de fechas inválido")
    return db.query(Appointment).filter(Appointment.professional_id == user.id, Appointment.starts_at < end, Appointment.ends_at > start).order_by(Appointment.starts_at).all()

def save_appointment(db, user, payload, appointment_id=None):
    # Serialize reservations for the same professional to prevent concurrent overlaps.
    db.execute(select(User.id).where(User.id == user.id).with_for_update()).scalar_one()
    appointment = None
    if appointment_id is not None:
        appointment = db.query(Appointment).filter(Appointment.id == appointment_id, Appointment.professional_id == user.id).first()
        if not appointment:
            raise HTTPException(404, "Cita no encontrada")
    own_patient(db, user, payload.patient_id)
    if payload.status not in ("cancelled", "no_show"):
        overlaps = db.query(Appointment).filter(Appointment.professional_id == user.id,
            Appointment.status.notin_(["cancelled", "no_show"]),
            Appointment.starts_at < payload.ends_at, Appointment.ends_at > payload.starts_at)
        if appointment_id:
            overlaps = overlaps.filter(Appointment.id != appointment_id)
        if overlaps.first():
            raise HTTPException(409, "Ya tienes una cita en ese horario")
    if appointment is None:
        appointment = Appointment(professional_id=user.id, **payload.model_dump())
        db.add(appointment)
    else:
        for key, value in payload.model_dump().items():
            setattr(appointment, key, value)
    db.commit()
    db.refresh(appointment)
    return appointment

@router.post("/appointments", response_model=AppointmentRead, status_code=201)
def create_appointment(payload: AppointmentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return save_appointment(db, user, payload)

@router.put("/appointments/{appointment_id}", response_model=AppointmentRead)
def update_appointment(appointment_id: int, payload: AppointmentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return save_appointment(db, user, payload, appointment_id)

@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"patients": db.query(Patient).filter(Patient.professional_id == user.id).count(),
            "visits": db.query(Visit).filter(Visit.professional_id == user.id).count()}

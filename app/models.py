from datetime import date, datetime
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, Enum as SQLEnum, ForeignKey, Integer, String, Text, func, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UserRole(str, Enum):
    admin = "admin"
    clinician = "clinician"
    reception = "reception"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), nullable=False, default=UserRole.clinician)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    session_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    specialty: Mapped[str] = mapped_column(String(120), default="Profesional de salud")
    phone: Mapped[str | None] = mapped_column(String(30))
    appointment_minutes: Mapped[int] = mapped_column(Integer, default=45)
    work_start: Mapped[str] = mapped_column(String(5), default="09:00")
    work_end: Mapped[str] = mapped_column(String(5), default="18:00")
    visits: Mapped[list["Visit"]] = relationship(back_populates="professional")


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    __table_args__ = (UniqueConstraint("professional_id", "rut", name="uq_patient_professional_rut"), CheckConstraint("age >= 0 AND age <= 120", name="ck_patient_age"))
    professional_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    rut: Mapped[str] = mapped_column(String(12), index=True, nullable=False)
    first_names: Mapped[str] = mapped_column(String(255), nullable=False)
    last_names: Mapped[str] = mapped_column(String(255), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    referral_source: Mapped[str | None] = mapped_column(String(255), nullable=True)

    pre_existing_conditions: Mapped[str] = mapped_column(Text, nullable=False)
    medications: Mapped[str | None] = mapped_column(Text, nullable=True)
    allergies: Mapped[str | None] = mapped_column(Text, nullable=True)
    pelvic_surgery_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    obstetric_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    gynecologic_history: Mapped[str | None] = mapped_column(Text, nullable=True)

    urinary_symptoms: Mapped[str | None] = mapped_column(Text, nullable=True)
    bowel_symptoms: Mapped[str | None] = mapped_column(Text, nullable=True)
    sexual_symptoms: Mapped[str | None] = mapped_column(Text, nullable=True)
    pain_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    red_flags: Mapped[str | None] = mapped_column(Text, nullable=True)

    consent_signed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    first_visit_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_visit_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    visits: Mapped[list["Visit"]] = relationship(back_populates="patient", cascade="all, delete-orphan")


class Visit(Base):
    __tablename__ = "visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    professional_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    visit_date: Mapped[date] = mapped_column(Date, nullable=False)

    chief_complaint: Mapped[str | None] = mapped_column(Text, nullable=True)
    objective_exam: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_findings: Mapped[str] = mapped_column(Text, nullable=False)
    clinical_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    treatment_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    home_exercises: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_visit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    pain_scale: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    patient: Mapped[Patient] = relationship(back_populates="visits")
    professional: Mapped[User] = relationship(back_populates="visits")



class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (CheckConstraint("ends_at > starts_at", name="ck_appointment_duration"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    professional_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MedicalOrder(Base):
    __tablename__ = "medical_orders"
    __table_args__ = (UniqueConstraint("patient_id", "sha256", name="uq_medical_order_patient_hash"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    professional_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    document_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    thumbnail_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    original_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AbuseState(Base):
    """Expiring counters and consumed form nonces; keys contain HMACs, never raw IP/email."""
    __tablename__ = "abuse_state"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    window_start: Mapped[int] = mapped_column(Integer, nullable=False)
    blocked_until: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False, index=True)


class PasswordReset(Base):
    __tablename__ = "password_resets"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    session_version: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

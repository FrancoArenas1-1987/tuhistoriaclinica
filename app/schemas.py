from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import UserRole
from app.services.rut import normalize_rut, validate_rut


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128, repr=False)


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    role: UserRole
    specialty: str = "Profesional de salud"
    phone: str | None = None
    appointment_minutes: int = 45
    work_start: str = "09:00"
    work_end: str = "18:00"
    is_active: bool = True


class UserRead(UserBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PatientBase(BaseModel):
    rut: str
    first_names: str = Field(min_length=2, max_length=255)
    last_names: str = Field(min_length=2, max_length=255)
    age: int = Field(ge=0, le=120)
    birth_date: date | None = None
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    occupation: str | None = None
    emergency_contact: str | None = None
    referral_source: str | None = None
    pre_existing_conditions: str = Field(min_length=3)
    medications: str | None = None
    allergies: str | None = None
    pelvic_surgery_history: str | None = None
    obstetric_history: str | None = None
    gynecologic_history: str | None = None
    urinary_symptoms: str | None = None
    bowel_symptoms: str | None = None
    sexual_symptoms: str | None = None
    pain_description: str | None = None
    red_flags: str | None = None
    consent_signed: bool = False
    first_visit_date: date
    last_visit_date: date | None = None

    @field_validator("rut")
    @classmethod
    def validate_rut_value(cls, value: str) -> str:
        if not validate_rut(value):
            raise ValueError("RUT invalido")
        return normalize_rut(value)


class PatientCreate(PatientBase):
    pass


class PatientRead(PatientBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VisitBase(BaseModel):
    patient_id: int
    visit_date: date
    chief_complaint: str | None = None
    objective_exam: str | None = None
    new_findings: str = Field(min_length=3)
    clinical_assessment: str | None = None
    treatment_plan: str | None = None
    home_exercises: str | None = None
    recommendations: str | None = None
    next_visit_date: date | None = None
    pain_scale: int | None = Field(default=None, ge=0, le=10)


class VisitCreate(VisitBase):
    pass


class VisitRead(VisitBase):
    id: int
    professional_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)



class RegisterRequest(BaseModel):
    form_token: str = Field(min_length=1, max_length=2048, repr=False)
    website: str = Field(default="", max_length=255, repr=False)
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=64)
    specialty: str = Field(min_length=2, max_length=120)

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value):
        if len(value.encode("utf-8")) > 72:
            raise ValueError("La contraseña no puede superar 72 bytes")
        return value


class ProfileUpdate(BaseModel):
    email: EmailStr | None = None
    current_password: str | None = Field(default=None, max_length=64, repr=False)
    full_name: str = Field(min_length=2, max_length=255)
    specialty: str = Field(min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    appointment_minutes: int = Field(ge=5, le=240)
    work_start: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    work_end: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def hours(self):
        if self.work_end <= self.work_start:
            raise ValueError("El horario de término debe ser posterior al inicio")
        return self


class AppointmentCreate(BaseModel):
    patient_id: int = Field(gt=0)
    starts_at: datetime
    ends_at: datetime
    reason: str | None = Field(default=None, max_length=2000)
    status: str = Field(default="scheduled", pattern="^(scheduled|confirmed|completed|cancelled|no_show)$")

    @model_validator(mode="after")
    def valid_dates(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("Las horas deben incluir zona horaria")
        if self.ends_at <= self.starts_at:
            raise ValueError("La hora de término debe ser posterior al inicio")
        if (self.ends_at-self.starts_at).total_seconds() > 86400:
            raise ValueError("La cita no puede durar más de 24 horas")
        return self


class AppointmentRead(AppointmentCreate):
    id: int
    professional_id: int
    model_config = ConfigDict(from_attributes=True)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=64, repr=False)
    new_password: str = Field(min_length=8, max_length=64, repr=False)
    confirm_password: str = Field(min_length=8, max_length=64, repr=False)

    @field_validator("current_password", "new_password", "confirm_password")
    @classmethod
    def valid_password_bytes(cls, value):
        if len(value.encode("utf-8")) > 72:
            raise ValueError("La contraseña no puede superar 72 bytes")
        return value

    @model_validator(mode="after")
    def matching_passwords(self):
        if self.new_password != self.confirm_password:
            raise ValueError("La nueva contraseña y su confirmación no coinciden")
        if self.new_password == self.current_password:
            raise ValueError("La nueva contraseña debe ser diferente de la actual")
        return self


class MedicalOrderRead(BaseModel):
    id: int
    patient_id: int
    title: str
    document_date: date | None
    notes: str | None
    size_bytes: int
    original_size_bytes: int
    width: int
    height: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

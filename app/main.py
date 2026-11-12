from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import engine, get_db
from app.routers import auth, clinic, medical_orders

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Gestión de pacientes, fichas clínicas y agenda para profesionales",
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def init_db() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.migration import MigrationContext
    config = Config(str(BASE_DIR.parent / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != head:
        raise RuntimeError("Base desactualizada. Ejecuta: python -m alembic upgrade head")



@app.on_event("startup")
def on_startup():
    init_db()


app.include_router(auth.router)
app.include_router(clinic.router)
app.include_router(medical_orders.router)


@app.get("/", response_class=HTMLResponse)
def public_home(request: Request):
    return templates.TemplateResponse(request=request, name="public/index.html", context={ "app_name": settings.app_name, "year": datetime.now(ZoneInfo("America/Santiago")).year})


@app.get("/registro", response_class=HTMLResponse)
@app.get("/ingresar", response_class=HTMLResponse)
@app.get("/portal", response_class=HTMLResponse)
def private_portal(request: Request):
    return templates.TemplateResponse(request=request, name="app/portal.html", context={ "app_name": settings.app_name, "year": datetime.now(ZoneInfo("America/Santiago")).year})


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}

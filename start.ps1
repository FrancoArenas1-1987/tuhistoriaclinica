$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "No se pudieron aplicar las migraciones. Revisa el tunel y .env." }
    python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
} finally {
    Pop-Location
}

"""Run integration tests on a temporary PostgreSQL DB, never on clinical data."""
import os
import subprocess
import sys
import time
import tempfile
import urllib.request
from uuid import uuid4
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from app.core.config import settings

url = make_url(settings.database_url)
if url.get_backend_name() != "postgresql":
    raise SystemExit("This runner requires PostgreSQL CREATE DATABASE privileges.")
name = "thc_qa_" + uuid4().hex
admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
env = {**os.environ, "DATABASE_URL": url.set(database=name).render_as_string(hide_password=False),
       "COOKIE_SECURE": "false", "ENVIRONMENT": "test"}
try:
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env)
    if result.returncode:
        raise SystemExit(result.returncode)
    print("Running against isolated temporary PostgreSQL DB", flush=True)
    if sys.argv[1:] == ["--browser"]:
        with tempfile.TemporaryDirectory() as storage:
            browser_env = {**env, "STORAGE_DIR": storage, "QA_BASE_URL": "http://127.0.0.1:8001"}
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001"], env=browser_env)
            try:
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(browser_env["QA_BASE_URL"] + "/health", timeout=1):
                            break
                    except Exception:
                        time.sleep(.2)
                else:
                    raise RuntimeError("Temporary QA server did not start")
                result = subprocess.run([sys.executable, "-m", "tests.browser_qa"], env=browser_env)
            finally:
                server.terminate()
                server.wait(timeout=15)
    else:
        result = subprocess.run([sys.executable, "-m", "unittest", *(sys.argv[1:] or ["discover", "-s", "tests", "-v"])], env=env)
    raise SystemExit(result.returncode)
finally:
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()
    print("Temporary database removed", flush=True)

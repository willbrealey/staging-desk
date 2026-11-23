"""Run the integration suite against a disposable PostgreSQL server."""
import os
from pathlib import Path
import secrets
import subprocess
from tempfile import TemporaryDirectory

import pgserver

with TemporaryDirectory(prefix="staging-postgres-") as tmp:
    server = pgserver.get_server(Path(tmp) / "database", cleanup_mode="delete")
    admin = server.get_uri()
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    config = conninfo_to_dict(admin)
    config.update(user="desk_runtime", password=secrets.token_urlsafe(24))
    runtime = make_conninfo(**config)
    environment = {**os.environ, "TEST_ADMIN_DATABASE_URL": admin, "DATABASE_URL": runtime}
    result = subprocess.run([os.sys.executable, "-m", "pytest", "tests/test_service.py", "-q"], env=environment)
    raise SystemExit(result.returncode)

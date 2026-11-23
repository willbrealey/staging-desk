"""Integration tests require an isolated, empty real PostgreSQL database."""
import hashlib
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from service.app import app
from workflow import ROOT, replay

ADMIN = os.environ["TEST_ADMIN_DATABASE_URL"]
RUNTIME = os.environ["DATABASE_URL"]
TENANTS = [uuid4(), uuid4()]
ACTORS = [uuid4(), uuid4()]
TOKENS = [secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(32)]
FINGERPRINT = replay(ROOT / "evidence/ready")["sha256"]


@pytest.fixture(scope="module", autouse=True)
def database():
    with psycopg.connect(ADMIN, autocommit=True) as conn:
        conn.execute((ROOT / "service/schema.sql").read_text())
        password = psycopg.conninfo.conninfo_to_dict(RUNTIME)["password"]
        conn.execute(sql.SQL("ALTER ROLE desk_runtime LOGIN PASSWORD {}").format(sql.Literal(password)))
        for i, token in enumerate(TOKENS):
            conn.execute("INSERT INTO desk.sessions VALUES (%s,%s,%s,%s)", (
                hashlib.sha256(token.encode()).hexdigest(), TENANTS[i % 2], ACTORS[i % 2],
                datetime.now(timezone.utc) + timedelta(hours=1 if i < 2 else -1)))
    yield


@pytest.fixture
def client():
    with TestClient(app) as test:
        yield test


def auth(i=0):
    return {"Authorization": "Bearer " + TOKENS[i]}


def body(**changes):
    return dict(id=str(uuid4()), case_id="ready", fingerprint=FINGERPRINT, decision="approved", **changes)


def test_auth_required_and_expired_tokens_fail(client):
    for headers in ({}, {"Authorization": "Bearer " + "x" * 44}, auth(2)):
        assert client.get("/approvals", headers=headers).status_code == 401


def test_tenant_cannot_read_other_tenant_decision_or_audit(client):
    request = body()
    created = client.post("/approvals", headers=auth(0), json=request)
    assert created.status_code == 201
    assert created.json()["tenant_id"] == str(TENANTS[0])
    assert created.json()["actor_id"] == str(ACTORS[0])
    assert client.get("/approvals/" + request["id"], headers=auth(1)).status_code == 404
    assert all(x["id"] != request["id"] for x in client.get("/approvals", headers=auth(1)).json())
    assert all(x["approval_id"] != request["id"] for x in client.get("/audit", headers=auth(1)).json())
    events = client.get("/audit", headers=auth(0)).json()
    assert len([x for x in events if x["approval_id"] == request["id"]]) == 1


def test_cannot_forge_identity_in_body_or_headers(client):
    forged = body()
    forged["tenant_id"] = str(TENANTS[1])
    assert client.post("/approvals", headers=auth(0), json=forged).status_code == 422
    forged.pop("tenant_id")
    result = client.post("/approvals", headers={**auth(0), "X-Tenant-ID": str(TENANTS[1])}, json=forged)
    assert result.json()["tenant_id"] == str(TENANTS[0])


def test_stale_or_blocked_proposal_has_no_audit_event(client):
    n = len(client.get("/audit", headers=auth()).json())
    invalid = body()
    invalid["fingerprint"] = "0" * 64
    assert client.post("/approvals", headers=auth(), json=invalid).status_code == 409
    invalid["case_id"] = "blocked"
    assert client.post("/approvals", headers=auth(), json=invalid).status_code == 422
    assert len(client.get("/audit", headers=auth()).json()) == n


def test_concurrent_retries_create_one_decision_and_event(client):
    request = body()
    def submit(_):
        return client.post("/approvals", headers=auth(), json=request).status_code
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(submit, range(8))) == [201] * 8
    events = client.get("/audit", headers=auth()).json()
    assert len([x for x in events if x["approval_id"] == request["id"]]) == 1
    request["decision"] = "changes"
    assert client.post("/approvals", headers=auth(), json=request).status_code == 409


def test_database_filters_without_application_where_clause(client):
    client.post("/approvals", headers=auth(), json=body())
    with psycopg.connect(RUNTIME) as conn:
        assert conn.execute("SELECT * FROM desk.approvals").fetchall() == []
        conn.execute("SELECT set_config('desk.tenant',%s,true)", (str(TENANTS[1]),))
        assert conn.execute("SELECT count(*) FROM desk.approvals WHERE tenant_id=%s", (TENANTS[0],)).fetchone()[0] == 0


def test_cross_tenant_insert_is_rejected_by_postgres():
    with psycopg.connect(RUNTIME) as conn:
        conn.execute("SELECT set_config('desk.tenant',%s,true)", (str(TENANTS[0]),))
        conn.execute("SELECT set_config('desk.actor',%s,true)", (str(ACTORS[0]),))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("INSERT INTO desk.approvals (tenant_id,id,case_id,fingerprint,decision) VALUES (%s,%s,'ready',%s,'approved')",
                         (TENANTS[1], uuid4(), FINGERPRINT))


@pytest.mark.parametrize("query", [
    "DELETE FROM desk.audit", "UPDATE desk.audit SET decision='changes'",
    "DELETE FROM desk.approvals", "SELECT * FROM desk.sessions",
    "INSERT INTO desk.audit (tenant_id,approval_id,actor_id,decision,fingerprint) SELECT tenant_id,id,actor_id,decision,fingerprint FROM desk.approvals",
])
def test_runtime_cannot_rewrite_audit_or_read_secrets(query):
    with psycopg.connect(RUNTIME) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(query)


def test_audit_failure_rolls_back_decision(client):
    request = body()
    with psycopg.connect(ADMIN) as conn:
        conn.execute("ALTER TABLE desk.audit ADD CONSTRAINT reject_test CHECK (decision <> 'approved') NOT VALID")
    try:
        with TestClient(app, raise_server_exceptions=False) as test:
            assert test.post("/approvals", headers=auth(), json=request).status_code == 500
        assert client.get("/approvals/" + request["id"], headers=auth()).status_code == 404
    finally:
        with psycopg.connect(ADMIN) as conn:
            conn.execute("ALTER TABLE desk.audit DROP CONSTRAINT reject_test")

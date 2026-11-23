import hashlib
import os
from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from workflow import ROOT, replay

app = FastAPI(title="Staging Desk approvals", docs_url="/docs")
bearer = HTTPBearer(auto_error=False)


def session(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if credentials is None or not 32 <= len(credentials.credentials) <= 256:
        raise HTTPException(401, "Valid bearer token required", headers={"WWW-Authenticate": "Bearer"})
    token_digest = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        role = conn.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        if role["rolsuper"] or role["rolbypassrls"]:
            raise HTTPException(503, "Service database role must enforce row security")
        identity = conn.execute("SELECT * FROM desk.authenticate(%s)", (token_digest,)).fetchone()
        if identity is None:
            raise HTTPException(401, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
        conn.execute("SELECT set_config('desk.tenant', %s, true)", (str(identity["tenant_id"]),))
        conn.execute("SELECT set_config('desk.actor', %s, true)", (str(identity["actor_id"]),))
        yield conn


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    case_id: Literal["ready"]
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["approved", "changes"]


Connection = Annotated[psycopg.Connection, Depends(session, scope="function")]


@app.post("/approvals", status_code=201)
def decide(body: Decision, conn: Connection):
    record = replay(ROOT / "evidence" / body.case_id)
    if record["status"] != "ready" or record["sha256"] != body.fingerprint:
        raise HTTPException(409, "Proposal has changed or failed verification")
    row = conn.execute(
        """INSERT INTO desk.approvals (id, case_id, fingerprint, decision)
           VALUES (%s,%s,%s,%s) ON CONFLICT (tenant_id,id) DO NOTHING RETURNING *""",
        (body.id, body.case_id, body.fingerprint, body.decision),
    ).fetchone()
    if row is None:
        row = conn.execute("SELECT * FROM desk.approvals WHERE id=%s", (body.id,)).fetchone()
        if any(row[key] != getattr(body, key) for key in ("case_id", "fingerprint", "decision")):
            raise HTTPException(409, "Decision id already belongs to another request")
    return row


@app.get("/approvals")
def approvals(conn: Connection):
    return conn.execute("SELECT * FROM desk.approvals ORDER BY created_at, id").fetchall()


@app.get("/approvals/{approval_id}")
def approval(approval_id: UUID, conn: Connection):
    row = conn.execute("SELECT * FROM desk.approvals WHERE id=%s", (approval_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Approval not found")
    return row


@app.get("/audit")
def audit(conn: Connection):
    return conn.execute("SELECT * FROM desk.audit ORDER BY created_at, id").fetchall()

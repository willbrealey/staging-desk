"""Issue an expiring API token using the separate migration credential."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import os
import secrets
from uuid import UUID

import psycopg

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--tenant", required=True, type=UUID)
parser.add_argument("--actor", required=True, type=UUID)
args = parser.parse_args()
token = secrets.token_urlsafe(32)
with psycopg.connect(os.environ["ADMIN_DATABASE_URL"]) as conn:
    conn.execute("INSERT INTO desk.sessions VALUES (%s,%s,%s,%s)", (
        hashlib.sha256(token.encode()).hexdigest(), args.tenant, args.actor,
        datetime.now(timezone.utc) + timedelta(hours=1)))
print(token)

# Run the approval service

The public GitHub Pages interface replays cases and saves decisions in browser storage. This API is a separate, runnable backend for durable approvals. CI exercises it against PostgreSQL 16.

## Verify without configuring a server

Requires Python 3.11+. From the repository root, create a virtual environment and install the service dependencies plus the optional local PostgreSQL binary package.

```sh
uv venv .venv
uv pip install --python .venv/bin/python -r service/requirements.txt pgserver==0.1.4
.venv/bin/python scripts/test_postgres_local.py
```

This creates a disposable real PostgreSQL database, provisions two tenants with random expiring credentials, runs the integration tests and removes the database. Tests cover cross-tenant SELECT without an application WHERE filter, rejected cross-tenant INSERT, unauthorized and expired tokens, forged identity, stale proposals, concurrent retries, restricted runtime grants and rollback when the audit write fails.

## Start a persistent instance

Use an empty PostgreSQL database for this sample. Set ADMIN_DATABASE_URL to its migration credential and DATABASE_URL to a separate desk_runtime login credential. Keep both outside Git. Apply the migration with the admin connection, enable runtime login, then assign a password interactively.

```sh
psql "$ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 -f service/schema.sql
psql "$ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 -c "ALTER ROLE desk_runtime LOGIN"
psql "$ADMIN_DATABASE_URL" -c '\password desk_runtime'
.venv/bin/python -m uvicorn service.app:app --host 127.0.0.1 --port 8000
```

The migration intentionally creates its objects once. Re-running it fails. Run the automated tests only against a fresh disposable database. Migration and token provisioning credentials belong to the operator. The API process only needs DATABASE_URL.

In a separate terminal, issue a one-hour credential for a synthetic tenant and actor. The command prints the token once. Avoid shared shell logs and clipboard history.

```sh
.venv/bin/python -m service.provision \
  --tenant 11111111-1111-4111-8111-111111111111 \
  --actor aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
```

At http://127.0.0.1:8000/docs, authorize with that token. GET /approvals and GET /audit return rows within that tenant. POST /approvals takes a caller-generated UUID id, case_id "ready", the current fingerprint from web/public/cases.json, and decision "approved" or "changes". The server replays the original evidence before accepting a decision. Reuse the same id to retry a request. Reusing it with different content returns 409. A new UUID records a new decision while preserving the old one.

## Security boundaries

Tokens are random, opaque, hashed in the database and expire after one hour. Revocation deletes their session row using the admin connection. API callers cannot read session hashes or supply their own tenant or actor. The API derives both from the token and sets them for the current transaction.

The runtime role has no superuser, table ownership or BYPASSRLS privilege. Both approval and audit tables use forced row-level security. The runtime can insert and read approvals and read audit events. It cannot update or delete either table. A restricted database trigger writes each audit row in the approval transaction. An audit error rolls back the decision. Concurrent identical retries write exactly one decision and one event.

Database connection credentials are trusted server secrets. A party holding the runtime database credential could set transaction context directly. RLS contains API query mistakes and authenticated cross-tenant requests. Protect the server credential and expose the database only to trusted services.

The sample has operator-issued credentials and no hosted identity provider or 2FA. TLS, identity onboarding, operational alerts, backup restores and the clinical deployment policy remain deployment work.

## Enforced model budgets

The existing run_agent.py replays the live CLI workflow with two-call and timeout limits. To use token and spend checks, run bounded_agent.py with a provider API key in the environment and the chosen model’s current input and output prices per million tokens.

```sh
python3 bounded_agent.py examples/request.txt .preview-budgeted \
  --model "$MODEL" \
  --input-usd-per-million "$INPUT_RATE" \
  --output-usd-per-million "$OUTPUT_RATE" \
  --budget-usd 0.10
```

Before each generation, the runner asks the provider for the complete input token count, including the response schema. It reserves input cost plus the full 1,200-token output allowance. It refuses a request that would exceed two generations, 16,000 combined reserved tokens or the configured USD budget. It provides no tools and makes no automatic retries. Incomplete generation cannot pass the review gate. A failed provider call keeps its reservation. budget.json records reservations and the prices supplied.

Tests stub the provider to prove that over-budget inputs stop before generation. The checked-in live CLI outputs were produced before this runner was added. The API runner has not produced new checked-in live model evidence. Provider prices are operator inputs, so the USD bound assumes those prices are accurate. Input counting and HTTP calls each have a 30-second network timeout.

[PostgreSQL row security](https://www.postgresql.org/docs/16/ddl-rowsecurity.html) · [Provider token counting](https://developers.openai.com/api/docs/guides/token-counting)

#!/bin/sh
set -eu
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest -q
python3 workflow.py export --check
git diff --check
if [ -n "${TEST_ADMIN_DATABASE_URL:-}" ]; then
    python3 -m pytest tests/test_service.py -q
fi

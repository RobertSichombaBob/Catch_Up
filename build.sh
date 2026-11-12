#!/usr/bin/env bash
# Render build command. Stops at the first error so a broken deploy never goes live.
set -o errexit
set -o pipefail

pip install --upgrade pip
pip install -r requirements.txt

mkdir -p "${MEDIA_ROOT:-media}" 2>/dev/null || true
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py seed_catchup        # safe to re-run: only adds what is missing
python manage.py ensure_superuser    # creates your own admin from env vars, once
python manage.py check --deploy --fail-level ERROR

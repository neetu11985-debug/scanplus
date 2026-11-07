#!/bin/sh
set -eu
python -m pip install --no-cache-dir -r requirements-render.txt
# First manual deploy must test the actual installed runtime too.
export SCANPLUS_DB_PATH=':memory:'
export SCANPLUS_MODE='demo'
export SCANPLUS_STRIPE_TEST='0'
export PYTHONDONTWRITEBYTECODE='1'
python -c 'import gunicorn; assert gunicorn.__version__ == "26.2.0"'
# The reviewed source includes encrypted-storage and offline Postgres tests.
# requirements-render.txt includes their pinned runtime requirements.
python -c 'import cryptography, psycopg, psycopg_pool, dotenv'
python -m unittest discover -s tests -q

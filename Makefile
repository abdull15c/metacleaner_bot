.PHONY: install run-bot run-worker run-admin migrate

install:
	python3.11 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install bcrypt==4.0.1
	.venv/bin/pip install -r requirements.txt

migrate:
	.venv/bin/python -m alembic upgrade head
	.venv/bin/python scripts/seed_settings.py

admin-create:
	.venv/bin/python scripts/create_admin.py

run-bot:
	.venv/bin/python -m bot.main

run-worker:
	.venv/bin/celery -A workers.celery_app worker --loglevel=info -Q video,cleanup,broadcast --pool=solo

run-admin:
	.venv/bin/python -m admin

test:
	.venv/bin/python -m pytest tests/ -v --tb=short

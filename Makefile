PY := .venv/bin/python
MANAGE := $(PY) manage.py

.PHONY: setup test migrate sync check deploy-check lint shell dev requirements

setup: requirements
	$(MAKE) migrate
	$(MANAGE) createsuperuser

requirements:
	python3 -m venv .venv
	$(PY) -m pip install -r requirements-dev.txt

test:
	$(MANAGE) test apps

lint:
	$(PY) -m ruff check .

migrate:
	$(MANAGE) makemigrations
	$(MANAGE) migrate

sync:
	$(MANAGE) sync_trackings

check:
	$(MANAGE) check

deploy-check:
	$(MANAGE) check --deploy

shell:
	$(MANAGE) shell

dev:
	$(MANAGE) runserver
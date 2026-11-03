PYTHON ?= python3
VENV := backend/.venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest
export PYTHONPATH := backend

.PHONY: install backend frontend dev test e2e doctor verify clean

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -r backend/requirements.txt
	cd frontend && npm install
	cd frontend && npx playwright install --with-deps chromium || npx playwright install chromium

backend:
	PYTHONPATH=backend $(PY) -m madira.main

frontend:
	cd frontend && npm run dev

dev:
	@$(MAKE) -j2 backend frontend

test:
	PYTHONPATH=backend $(PYTEST) -q backend/tests

e2e:
	cd frontend && npx playwright test

doctor:
	@echo "== Madira doctor =="
	@PYTHONPATH=backend $(PY) -c "from madira.config import status_payload; import json; print(json.dumps(status_payload(), indent=2))"
	@curl -sf http://127.0.0.1:8123/health || echo "backend not running (start with make backend)"
	@curl -sf http://127.0.0.1:3000 >/dev/null && echo "frontend ok" || echo "frontend not running (start with make frontend)"

verify: test
	@echo "Start make dev, then make e2e (or follow .cursor/skills/verify-madira)."

clean:
	rm -rf backend/data/madira.db frontend/.next test-results playwright-report

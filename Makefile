PY ?= .venv/bin/python
PIP ?= .venv/bin/pip

BASE ?= http://localhost:8000

.PHONY: demo-outcomes sweep e2e a11y install data clean-data vectors match all eval app test create-admin demo-users backup docker-build docker-up

install:
	test -d .venv || python3 -m venv .venv
	$(PY) -m pip install -r requirements.txt && $(PY) -m pip install -e .
	cd web && npm install

data:
	$(PY) -m matcher.generate_students && $(PY) -m matcher.generate_opportunities

clean-data:
	$(PY) -m matcher.clean

vectors:
	$(PY) -m matcher.embed

match:
	$(PY) -m matcher.score && $(PY) -m matcher.rank && $(PY) -m matcher.explain

all:
	$(PY) -m matcher.pipeline

eval:
	test -f eval/labels.csv || ($(PY) -m eval.make_label_sheet && $(PY) -m eval.auto_label)
	$(PY) -m eval.evaluate

app:
	@echo "API on http://localhost:8000  and web app on http://localhost:5173"
	DEMO_LOGIN=1 $(PY) -m uvicorn api.server:app --port 8000 & cd web && npm run dev

test:
	$(PY) -m pytest -q

create-admin:
	@test -n "$(USER_NAME)" || (echo "Usage: make create-admin USER_NAME=yourname" && exit 1)
	$(PY) -m matcher.accounts create-admin --username $(USER_NAME)

demo-users:
	@test -n "$(DEMO_PASSWORD)" || (echo "Usage: make demo-users DEMO_PASSWORD='a long demo password'" && exit 1)
	DEMO_PASSWORD="$(DEMO_PASSWORD)" $(PY) -m matcher.accounts seed-demo

demo-outcomes:
	$(PY) -m matcher.accounts seed-outcomes

backup:
	$(PY) -m matcher.accounts backup backups

docker-build:
	docker compose build

docker-up:
	docker compose up -d

sweep:
	$(PY) -m eval.sweep --base $(BASE) $(if $(PASSWORD),--password "$(PASSWORD)")

e2e:
	cd web && npm run e2e

a11y:
	cd web && npm run a11y

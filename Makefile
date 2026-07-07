.PHONY: install db db-down api sync sync-clear docker-up docker-down compile clean test chat search gaps injection-test

VENV := .venv/bin

install:
	python3 -m venv .venv
	$(VENV)/pip install -e .
	test -f .env || cp .env.example .env

db:
	docker compose up -d postgres

db-down:
	docker compose down

api:
	$(VENV)/uvicorn tr4.app:app --reload --host 127.0.0.1 --port 8000

sync:
	$(VENV)/tr4-sync --whatsapp ./data/raw/grupo.txt --facebook-json ./data/raw/fb.json \
		--facebook-manual ./data/facebook_manual --docs ./data/manuals --owner-notes ./data/notes \
		--web-seeds ./data/seeds/tr4_sources.txt

sync-clear:
	$(VENV)/tr4-sync --whatsapp ./data/raw/grupo.txt --facebook-json ./data/raw/fb.json \
		--facebook-manual ./data/facebook_manual --docs ./data/manuals --owner-notes ./data/notes \
		--web-seeds ./data/seeds/tr4_sources.txt --clear

docker-up:
	docker compose up -d

docker-down:
	docker compose down

compile:
	$(VENV)/python3 -m py_compile src/tr4/*.py src/tr4/ingest/*.py src/tr4/jobs/*.py

# Smoke test against a running local API (`make db` + `make api` first, in other shells).
# MESSAGE="..." make test to ask something else.
MESSAGE ?= qual pneu original do pajero tr4?
test:
	@set -a; [ -f .env ] && . ./.env; set +a; \
	echo "== /health =="; curl -s http://127.0.0.1:8000/health; echo; \
	echo "== /terms =="; curl -s http://127.0.0.1:8000/terms; echo; \
	echo "== /chat (sem accepted_terms, deve dar 403) =="; \
	curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/chat \
		-H "Content-Type: application/json" -H "X-API-Key: $$TR4_API_KEY" \
		-d '{"message":"oi"}'; \
	echo "== /chat =="; \
	curl -s -X POST http://127.0.0.1:8000/chat \
		-H "Content-Type: application/json" -H "X-API-Key: $$TR4_API_KEY" \
		-d "{\"message\": \"$(MESSAGE)\", \"accepted_terms\": true}"; echo

clean:
	find . -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} +

# Interactive local chat (`make db` + `make api` first, in other shells).
chat:
	@set -a; [ -f .env ] && . ./.env; set +a; $(VENV)/python3 scripts/chat_cli.py

# Test retrieval only against data already indexed — no Groq, no API server, no cost.
# Needs `make db` running (+ Ollama for embeddings).
search:
	@set -a; [ -f .env ] && . ./.env; set +a; $(VENV)/python3 scripts/search_cli.py

# Questions the bot likely answered poorly — decide what to research/ingest next.
gaps:
	@set -a; [ -f .env ] && . ./.env; set +a; $(VENV)/python3 scripts/gaps_report.py

# Adversarial/prompt-injection test suite — needs a real GROQ_API_KEY to give real signal.
injection-test:
	@set -a; [ -f .env ] && . ./.env; set +a; $(VENV)/python3 scripts/injection_tests.py

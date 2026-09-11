.PHONY: up down logs migrate revision test lint fmt shell

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f api worker-cpu worker-gpu worker-tts

migrate:
	docker compose run --rm api alembic upgrade head

revision:
	docker compose run --rm api alembic revision --autogenerate -m "$(m)"

test:
	pip install -r requirements-dev.txt --break-system-packages -q
	pytest -v --cov=app

lint:
	ruff check app tests

fmt:
	ruff check --fix app tests

shell:
	docker compose run --rm api python

.PHONY: help up stop logs clean test lint tools

help:
	@echo "Available commands:"
	@echo "  up          - Start all services"
	@echo "  stop        - Stop all services"
	@echo "  logs        - Show logs"
	@echo "  tools       - Start with Redis Commander"
	@echo "  clean       - Remove all containers and volumes"
	@echo "  test        - Run tests"
	@echo "  lint        - Run linting"

up:
	docker-compose up --build

stop:
	docker-compose down

logs:
	docker-compose logs -f

tools:
	docker-compose --profile tools up --build

clean:
	docker-compose down -v
	docker system prune -f

test:
	docker-compose exec app uv run pytest

lint:
	docker-compose exec app uv run ruff check .
	docker-compose exec app uv run mypy app/

# Local development (without Docker)
local-dev:
	uv sync
	uv run python -m app.main

local-test:
	uv run pytest

local-lint:
	uv run ruff check .
	uv run mypy app/

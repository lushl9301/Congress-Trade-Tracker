.PHONY: help install init test clean run-ingest run-signals run-trade run-daily status

help:
	@echo "Congress Trade Tracker - Makefile"
	@echo ""
	@echo "Available commands:"
	@echo "  make install      - Install dependencies"
	@echo "  make init         - Initialize database"
	@echo "  make test         - Run tests"
	@echo "  make clean        - Clean temporary files"
	@echo "  make run-ingest   - Fetch congressional trades"
	@echo "  make run-signals  - Generate trading signals"
	@echo "  make run-trade    - Execute trades"
	@echo "  make run-daily    - Run daily pipeline"
	@echo "  make status       - Show system status"

install:
	pip install -r requirements.txt

init:
	python -m app.run init-db

test:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=app --cov-report=html --cov-report=term

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.pyo' -delete
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage

run-ingest:
	python -m app.run ingest

run-signals:
	python -m app.run signals

run-trade:
	python -m app.run trade

run-daily:
	python -m app.run daily

status:
	python -m app.run status

reconcile:
	python -m app.run reconcile

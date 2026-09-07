# KW water main break risk -- developer entry points.
#
# Phase 0-1 targets only. Phase 2 adds `transform`, phase 4 adds `train`.

PY := .venv/bin/python

.PHONY: help setup extract extract-breaks extract-mains extract-weather \
        deps transform transform-test docs build test lint fmt clean

help:
	@grep -E "^[a-z-]+:.*?## .*$$" $(MAKEFILE_LIST) | sed "s/:.*## /\t/" | expand -t22

setup:  ## Create .venv and install the package with dev extras
	python3.11 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"

extract:  ## Extract all raw datasets to data/raw/ (hits the live APIs)
	$(PY) -m extract.run --dataset all

extract-breaks:  ## Extract the water main breaks layer only
	$(PY) -m extract.run --dataset water_main_breaks

extract-mains:  ## Extract the water mains inventory only
	$(PY) -m extract.run --dataset water_mains

extract-weather:  ## Extract the spliced ECCC daily climate series only
	$(PY) -m extract.run --dataset weather_daily

deps:  ## Install dbt package dependencies
	cd transform && ../$(PY) -m dbt.cli.main deps --profiles-dir .

transform:  ## Build the warehouse (models only, no tests)
	cd transform && ../$(PY) -m dbt.cli.main run --profiles-dir .

transform-test:  ## Run dbt data tests only
	cd transform && ../$(PY) -m dbt.cli.main test --profiles-dir .

docs:  ## Generate and serve the dbt lineage docs
	cd transform && ../$(PY) -m dbt.cli.main docs generate --profiles-dir . && \
		../$(PY) -m dbt.cli.main docs serve --profiles-dir .

build:  ## Full pipeline: extract -> snapshot -> models -> tests
	$(MAKE) extract
	cd transform && ../$(PY) -m dbt.cli.main build --profiles-dir .

test:  ## Run the offline python test suite
	$(PY) -m pytest

lint:  ## Lint with ruff
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

fmt:  ## Auto-format with ruff
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

clean:  ## Remove caches (leaves data/ and .venv alone)
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache

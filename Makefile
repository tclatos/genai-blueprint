# cSpell: disable
# GenAI Blueprint -- project Makefile.
# All shared targets (install, fmt, lint, test, clean, rebase, ...) come from
# tk_makefile.mk which mirrors genai-tk/Makefile.  Only project-specific
# variables and targets belong here.

##############################
##  Project variables
##############################
APP            = genai-blueprint
PKG_NAME       = genai_blueprint
IMAGE_VERSION  = 0.2a
AWS_REGION     = eu-west-1
AWS_ACCOUNT_ID = 909658914353
STREAMLIT_ENTRY = genai_blueprint/main/streamlit.py
MODAL_ENTRY     = genai_blueprint/main/modal_app.py

# PYTHONPATH when running against a local genai-tk source checkout.
# Falls back gracefully when genai-tk is only present in .venv.
DEV_PYTHONPATH = ../genai-tk:.:$(PWD)

all: help

##############################
##  Includes
##############################
include tk_makefile.mk   # genai-tk standard targets (install/fmt/lint/test/clean/...)
include deploy/docker.mk
# include deploy/aws.mk
# include deploy/modal.mk

##############################
##  Web Applications
##############################
.PHONY: webapp fast-api langserve

webapp:  ## Launch Streamlit app
	PYTHONPATH=$(DEV_PYTHONPATH) uv run streamlit run "$(STREAMLIT_ENTRY)"

fast-api:  ## Launch FastAPI server locally
	uvicorn $(FASTAPI_ENTRY_POINT) --reload

# langserve:  ## Launch LangServe app
# 	PYTHONPATH=$(DEV_PYTHONPATH) uv run python genai_blueprint/main/langserve_app.py


##############################
##  Infrastructure
##############################
.PHONY: postgres chrome

postgres:  ## Start Postgres + pgvector container
	docker rm -f pgvector-container 2>/dev/null || true
	docker run -d --name pgvector-container \
		-e POSTGRES_USER=$(POSTGRES_USER) \
		-e POSTGRES_PASSWORD=$(POSTGRES_PASSWORD) \
		-e POSTGRES_DB=ekg \
		-p 5432:5432 \
		-v /home/tcl/pgvector-data:/var/lib/postgresql/data \
		pgvector/pgvector:pg17

chrome:  ## Start Chromium container (UI at http://localhost:3000)
	docker rm -f chromium 2>/dev/null || true
	docker run -d --name=chromium \
		--security-opt seccomp=unconfined \
		-e PUID=1000 -e PGID=1000 -e TZ=Europe/Paris \
		-p 3000:3000 -p 3001:3001 \
		-v /home/tcl/.chromiun:/config \
		--shm-size="1gb" --restart unless-stopped \
		lscr.io/linuxserver/chromium:latest
	xdg-open localhost:3000

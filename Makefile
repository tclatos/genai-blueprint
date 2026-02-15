# This Makefile provides commands for:
# - Development environment setup
# - Docker image building and deployment
# - Cloud platform integration (GCP, Azure, Modal)
# - Project maintenance tasks
#
# Usage: make [target]
#cSpell: disable


STREAMLIT_ENTRY_POINT="genai_blueprint/main/streamlit.py"
MODAL_ENTRY_POINT="genai_blueprint/main/modal_app.py"
APP=genai-blueprint
IMAGE_VERSION=0.2a
AWS_REGION=eu-west-1
AWS_ACCOUNT_ID=909658914353

# Development PYTHONPATH for local genai-tk development
# Assumes project structure: parent/genai-tk and parent/genai-blueprint
# For different structures, override with: make target DEV_PYTHONPATH="/custom/path/genai-tk:.:$(PWD)"
DEV_PYTHONPATH="../genai-tk:.:$(PWD)"

all: help 

MAKEFLAGS += --warn-undefined-variables                                                            
SHELL     := bash -euo pipefail -c   # exit on error, undefined var, pipefail 

# Guard against GNU/Make vs BSD/Make incompatibilities 
# ifneq ($(shell echo 'a b' | xargs -n1 echo 2>/dev/null | wc -l),2)                                 
#   $(error You need GNU xargs)                                                                      
# endif

# .env file discovery - check most common locations first
ENV_FILE := $(shell \
	if [ -f ".env" ]; then echo "$(CURDIR)/.env"; \
	elif [ -f "../.env" ]; then echo "$(CURDIR)/../.env"; \
	elif [ -f "../../.env" ]; then echo "$(CURDIR)/../../.env"; \
	else echo ""; fi)
ifneq ($(ENV_FILE),)
include $(ENV_FILE)
else
$(warning .env file not found in current or parent directories)
endif


include deploy/docker.mk
#include deploy/aws.mk
#include deploy/github.mk
#include deploy/modal.mk

.PHONY: .uv   .pre-commit .pythonpath show-dev-path benchmark
.uv:  ## Check that uv is installed
	@uv -V || echo 'Please install uv: curl -LsSf https://astral.sh/uv/install.sh | sh 

.pre-commit: .uv  ## Check that pre-commit is installed    see https://pre-commit.com/
	@uv run pre-commit -V || uv pip install pre-commit

.pythonpath:
	@if [ -z "$(PYTHONPATH)" ]; then \
		echo "Warning: PYTHONPATH is not set. Consider to put somewhere: export PYTHONPATH=\".\" "; \
	fi

show-dev-path: ## Show current DEV_PYTHONPATH setting
	@echo "Current DEV_PYTHONPATH: $(DEV_PYTHONPATH)"
	@echo "Checking genai-tk availability: $$([ -d ../genai-tk ] && echo 'EXISTS' || echo 'NOT FOUND')"
	@echo "Usage: make webapp (uses DEV_PYTHONPATH) or make test-install"


##############################
##  GenAI Blueprint related commands
##############################
.PHONY: fast_api langserve webapp 
fast-api: ## langsLauch FastAPI server localy
	uvicorn $(FASTAPI_ENTRY_POINT) --reload

langserve: ## Lauch langserve app
	PYTHONPATH=$(DEV_PYTHONPATH) uv run python genai_blueprint/main/langserve_app.py

webapp: ## Launch Streamlit app
	PYTHONPATH=$(DEV_PYTHONPATH) uv run streamlit run "$(STREAMLIT_ENTRY_POINT)"

##############################
##  Deer-flow Integration
##############################
DEER_FLOW_REPO=https://github.com/bytedance/deer-flow.git
DEER_FLOW_DIR=ext/deer-flow

.PHONY: deer-flow-sync deer-flow-install
deer-flow-sync: ## Clone or update Deer-flow repository
	@if [ -d "$(DEER_FLOW_DIR)" ]; then \
		echo "Updating Deer-flow..."; \
		cd $(DEER_FLOW_DIR) && git pull --rebase; \
	else \
		echo "Cloning Deer-flow..."; \
		mkdir -p ext; \
		git clone --depth 1 $(DEER_FLOW_REPO) $(DEER_FLOW_DIR); \
	fi
	@echo "Deer-flow synced at $(DEER_FLOW_DIR)"

deer-flow-install: deer-flow-sync ## Sync Deer-flow and install dependencies
	uv sync --group deerflow
	@echo "Deer-flow ready. Backend at: $(DEER_FLOW_DIR)/backend"


##############################
##  Development
##############################
.PHONY: rebase aider aider-haiku aider-r1 lint quality clean_notebooks 
rebase: ## Sync local repo with remote one (changes are stashed before!)
	git fetch origin
	git stash
	git rebase origin/main
	uv sync --upgrade-package genai-tk

lint: ## Run Ruff an all Python files to format fix imports
	ruff check --select I --fix
	ruff format


quality: ## Run Ruff on all Python files to check quality (fast version)
	@echo "Running ruff on Python files (excluding .venv and wip)..."
	ruff check --fix --exclude .venv --exclude genai_blueprint/wip .

clean-notebooks: ## Clean Jupyter notebook outputs.
	@find . -path "./.venv" -prune -o -name "*.ipynb" -print | while read -r notebook; do \
		echo "Cleaning outputs from: $$notebook"; \
		uv run --with nbconvert python -m nbconvert --clear-output --inplace "$$notebook"; \
	done

##############################
##  Telemetry  Tasks
##############################
# .PHONY: telemetry

# telemetry:  ## Run Phoenix telemetry server in background
# 	@echo "Starting Phoenix telemetry server..."
# 	@if ! pgrep -f "phoenix.server.main" > /dev/null; then \
# 		python -m phoenix.server.main serve > /tmp/phoenix.log 2>&1 & \
# 		echo "Phoenix server started in background (PID: $$!)"; \
# 		echo "Logs are being written to /tmp/phoenix.log"; \
# 		echo "look at: http://localhost:6006/projects" \
# 	else \
# 		echo "Phoenix server is already running"; \
# 	fi

##############################
##  uv and project  install
##############################

.PHONY: check-uv install

check-uv: ## Check if uv is installed, install if missing
	@if command -v uv >/dev/null 2>&1; then \
		echo "uv is already installed"; \
	else \
		echo "uv is not installed. Installing now..."; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
		echo "uv installed successfully"; \
		. $HOME/.local/bin/env; \
	fi

install: check-uv   ## Install SW
	uv sync

##############
##  MISC  ###
##############

.PHONY: clean clean-notebooks clean-history help postgres chrome qwen show-dev-path

clean:  ## Clean Python bytecode and cache files
	@echo "Cleaning UV cache and Python artifacts..."
	uv cache prune
	@# Single find command for all cleanup operations
	find . \( -name "*.py[co]" -o -name "__pycache__" -o -name ".ruff_cache" -o -name ".mypy_cache" \) -exec rm -rf {} + 2>/dev/null || true

clean-history: ## Remove duplicate entries and common commands from .bash_history
	@if [ -f ~/.bash_history ]; then \
		awk '!/^(ls|cat|hgrep|h|cd|p|m|ll|pwd|code|mkdir|export|rmdir|uv tree|make)( |$$)/ && !seen[$$0]++' ~/.bash_history > ~/.bash_history_unique && \
		mv ~/.bash_history_unique ~/.bash_history; \
		echo "Done : duplicates and common commands removed. \nRun 'history -c; history -r' in your shell to reload the cleaned history"; \
	else \
		echo "No .bash_history file found"; \
	fi                                                                                                  

help:                                                                                                                                          
	@echo "Available targets:"                                                                                                                  
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST) | sort 


test-install: .pythonpath ## Quick test install
	@if [ -z "$(PYTHONPATH)" ]; then \
		echo -e "\033[33mWarning: PYTHONPATH is not set. Consider setting: export PYTHONPATH=\".\"\033[0m"; \
	else \
		echo -e "\033[32mPYTHONPATH is set to: $(PYTHONPATH)\033[0m"; \
	fi
	@echo -e "\033[3m\033[36mCall a fake LLM that returns the prompt. Here it should display 'tell me a joke on ...'\033[0m"
	echo bears | PYTHONPATH=$(DEV_PYTHONPATH) uv run cli core run joke -m parrot_local_fake


##############################
##  Project specific commands
##############################

##############################
##  MICS
##############################

postgres:   ## Start docker Postgres + pgvector                                                                           
	docker rm -f pgvector-container 2>/dev/null || true
	docker run -d --name pgvector-container \
		-e POSTGRES_USER=$(POSTGRES_USER) -e POSTGRES_PASSWORD=$(POSTGRES_PASSWORD) -e POSTGRES_DB=ekg \
		-p 5432:5432 \
		-v /home/tcl/pgvector-data:/var/lib/postgresql/data \
		pgvector/pgvector:pg17

chrome:  ## Start docker Chromium 
# see https://hub.docker.com/r/linuxserver/chromium
	docker rm -f chromium 2>/dev/null || true
	docker run -d --name=chromium \
	--security-opt seccomp=unconfined  -e PUID=1000 -e PGID=1000 -e TZ=Europe/Paris  \
	-p 3000:3000 -p 3001:3001 -v /home/tcl/.chromiun:/config \
	--shm-size="1gb" --restart unless-stopped \
	lscr.io/linuxserver/chromium:latest
	xdg-open localhost:3000

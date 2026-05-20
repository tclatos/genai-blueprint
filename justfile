# GenAI Blueprint — project justfile
# Shared recipes imported from genai-tk/tk.just.
# Project-specific recipes defined here.

set dotenv-load
set shell := ["bash", "-euc"]
set positional-arguments

pkg_name := "genai_blueprint"
app := "genai-blueprint"
image_version := "0.2a"
aws_region := "eu-west-1"
aws_account_id := "909658914353"
streamlit_entry := "genai_blueprint/main/streamlit.py"
modal_entry := "genai_blueprint/main/modal_app.py"
dev_pythonpath := "../genai-tk:.:${PWD}"

# Import shared genai-tk recipes
import '../genai-tk/tk.just'

# Import deployment modules
mod docker 'deploy/docker.just'
mod aws 'deploy/aws.just'
mod modal 'deploy/modal.just'

# List available recipes
default:
    @just --list --unsorted

# ─── Web Applications ───────────────────────────────────────────────────────

[doc('Launch Streamlit app')]
webapp:
    PYTHONPATH={{ dev_pythonpath }} uv run streamlit run "{{ streamlit_entry }}"

[doc('Launch FastAPI server locally')]
fast-api:
    PYTHONPATH={{ dev_pythonpath }} uv run uvicorn genai_blueprint.main.fastapi_app:app --reload

# ─── Infrastructure ─────────────────────────────────────────────────────────

[doc('Start Postgres + pgvector container')]
postgres:
    docker rm -f pgvector-container 2>/dev/null || true
    docker run -d --name pgvector-container \
        -e POSTGRES_USER=${POSTGRES_USER} \
        -e POSTGRES_PASSWORD=${POSTGRES_PASSWORD} \
        -e POSTGRES_DB=ekg \
        -p 5432:5432 \
        -v /home/tcl/pgvector-data:/var/lib/postgresql/data \
        pgvector/pgvector:pg17

[doc('Start Chromium container (UI at http://localhost:3000)')]
chrome:
    docker rm -f chromium 2>/dev/null || true
    docker run -d --name=chromium \
        --security-opt seccomp=unconfined \
        -e PUID=1000 -e PGID=1000 -e TZ=Europe/Paris \
        -p 3000:3000 -p 3001:3001 \
        -v /home/tcl/.chromiun:/config \
        --shm-size="1gb" --restart unless-stopped \
        lscr.io/linuxserver/chromium:latest
    xdg-open localhost:3000

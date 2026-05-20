# Docker deployment recipes for genai-blueprint

set dotenv-load
set shell := ["bash", "-euc"]

app := "genai-blueprint"
image_version := "0.2a"

[doc('Build the Docker image')]
build:
    docker build --pull --rm -f "deploy/Dockerfile" -t {{ app }}:{{ image_version }} "."

[doc('Run the container with environment variables and mounted data')]
run:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Loading environment variables from .env file"
    echo "Mounting external data from ${ONEDRIVE}/_ongoing/training_GenAI/"
    docker run -it -p 8501:8501 \
        --env-file .env \
        -e REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
        -e SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
        -e CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
        -v "${ONEDRIVE}/_ongoing/training_GenAI/:/data/external" \
        {{ app }}:{{ image_version }}

[doc('Check if the image is built')]
check:
    docker images -a | grep {{ app }} || echo "No image found for {{ app }}"

[doc('Sync time (needed for WSL after hibernation)')]
sync-time:
    sudo hwclock -s

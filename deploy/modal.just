# Modal deployment recipes for genai-blueprint
# WIP - not fully working yet

set dotenv-load
set shell := ["bash", "-euc"]

app := "genai-blueprint"
image_version := "0.2a"
aws_region := "eu-west-1"
aws_account_id := "909658914353"
modal_entry := "genai_blueprint/main/modal_app.py"

[doc('Install Modal CLI')]
install:
    uv pip install modal

[doc('Login to Modal')]
login:
    modal token new

[doc('Deploy to Modal (code mode)')]
deploy:
    MODAL_DEPLOYMENT_MODE=code uv run modal deploy {{ modal_entry }}

[doc('Deploy to Modal using AWS ECR image')]
deploy-aws:
    MODAL_DEPLOYMENT_MODE=aws_image \
    MODAL_AWS_IMAGE_URI={{ aws_account_id }}.dkr.ecr.{{ aws_region }}.amazonaws.com/{{ app }}:{{ image_version }} \
    modal deploy {{ modal_entry }}

[doc('Serve Modal locally (code mode)')]
serve:
    MODAL_DEPLOYMENT_MODE=code modal serve {{ modal_entry }}

[doc('Deploy to Modal with forced image rebuild')]
deploy-force:
    modal image clear
    MODAL_DEPLOYMENT_MODE=code modal deploy {{ modal_entry }}

[doc('Deploy to Modal with forced rebuild (AWS image)')]
deploy-force-aws:
    modal image clear
    MODAL_DEPLOYMENT_MODE=aws_image \
    MODAL_AWS_IMAGE_URI={{ aws_account_id }}.dkr.ecr.{{ aws_region }}.amazonaws.com/{{ app }}:{{ image_version }} \
    modal deploy {{ modal_entry }}

# AWS deployment recipes for genai-blueprint

set dotenv-load
set shell := ["bash", "-euc"]

app := "genai-blueprint"
image_version := "0.2a"
aws_region := "eu-west-1"
aws_account_id := "909658914353"
aws_subnet := "subnet-09ea60865f6ded152"
aws_security_group := "sg-0f9ae86b1de2e3956"

[doc('Push Docker image to AWS ECR')]
push:
    aws ecr create-repository --repository-name {{ app }} --region {{ aws_region }} || true
    aws ecr get-login-password --region {{ aws_region }} | docker login --username AWS --password-stdin {{ aws_account_id }}.dkr.ecr.{{ aws_region }}.amazonaws.com
    docker tag {{ app }}:{{ image_version }} {{ aws_account_id }}.dkr.ecr.{{ aws_region }}.amazonaws.com/{{ app }}:{{ image_version }}
    docker push {{ aws_account_id }}.dkr.ecr.{{ aws_region }}.amazonaws.com/{{ app }}:{{ image_version }}

[doc('Deploy to AWS ECS Fargate')]
deploy:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Creating ECS cluster..."
    aws --no-cli-pager ecs create-cluster --cluster-name {{ app }}-cluster --region {{ aws_region }} || true

    echo "Creating CloudWatch log group..."
    aws --no-cli-pager logs create-log-group \
        --log-group-name "/ecs/{{ app }}-task" \
        --region {{ aws_region }} || true

    echo "Updating security group to allow HTTP traffic..."
    aws --no-cli-pager ec2 authorize-security-group-ingress \
        --group-id {{ aws_security_group }} \
        --ip-permissions '[{"IpProtocol": "tcp", "FromPort": 8501, "ToPort": 8501, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]' \
        --region {{ aws_region }} || true

    echo "Creating task definition..."
    SECRETS_JSON=$(./deploy/generate_container_secrets.sh {{ app }} {{ aws_region }} {{ aws_account_id }} .env)
    aws --no-cli-pager ecs register-task-definition \
        --family {{ app }}-task \
        --network-mode awsvpc \
        --cpu "256" \
        --memory "512" \
        --requires-compatibilities "FARGATE" \
        --execution-role-arn arn:aws:iam::{{ aws_account_id }}:role/ecsTaskExecutionRole \
        --task-role-arn arn:aws:iam::{{ aws_account_id }}:role/ecsTaskRole \
        --container-definitions "[{\"name\":\"{{ app }}-container\",\"image\":\"{{ aws_account_id }}.dkr.ecr.{{ aws_region }}.amazonaws.com/{{ app }}:{{ image_version }}\",\"portMappings\":[{\"containerPort\":8501,\"hostPort\":8501}],\"essential\":true,\"secrets\":$SECRETS_JSON,\"healthCheck\":{\"command\":[\"CMD-SHELL\",\"curl -f http://localhost:8501/_stcore/health || exit 1\"],\"interval\":30,\"timeout\":5,\"retries\":3},\"logConfiguration\":{\"logDriver\":\"awslogs\",\"options\":{\"awslogs-group\":\"/ecs/{{ app }}-task\",\"awslogs-region\":\"{{ aws_region }}\",\"awslogs-stream-prefix\":\"ecs\"}}}]" \
        --region {{ aws_region }}

    echo "Creating or updating ECS service..."
    aws --no-cli-pager ecs create-service \
        --cluster {{ app }}-cluster \
        --service-name {{ app }}-service \
        --task-definition {{ app }}-task \
        --desired-count 1 \
        --launch-type "FARGATE" \
        --enable-execute-command \
        --network-configuration "awsvpcConfiguration={subnets=[{{ aws_subnet }}],securityGroups=[{{ aws_security_group }}],assignPublicIp=ENABLED}" \
        --region {{ aws_region }} || \
    aws --no-cli-pager ecs update-service \
        --cluster {{ app }}-cluster \
        --service {{ app }}-service \
        --task-definition {{ app }}-task \
        --desired-count 1 \
        --enable-execute-command \
        --region {{ aws_region }}

    echo "Application deployed! Access it at the public IP on port 8501."

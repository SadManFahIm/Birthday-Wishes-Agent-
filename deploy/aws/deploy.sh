#!/bin/bash
# ══════════════════════════════════════════════
# deploy/aws/deploy.sh
# AWS ECS-এ Birthday Agent deploy করার script
#
# Requirements:
#   - AWS CLI installed & configured (aws configure)
#   - Docker installed
#   - Docker Hub account
#
# Usage:
#   chmod +x deploy/aws/deploy.sh
#   ./deploy/aws/deploy.sh
# ══════════════════════════════════════════════

set -e  # Exit on any error

# ── Config (এগুলো তোমার নিজের values দিয়ে replace করো) ──
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID="YOUR_ACCOUNT_ID"
DOCKER_USERNAME="YOUR_DOCKERHUB_USERNAME"
IMAGE_NAME="birthday-agent"
ECS_CLUSTER="birthday-agent-cluster"
ECS_SERVICE="birthday-agent-service"
LOG_GROUP="/ecs/birthday-agent"

echo "🚀 Birthday Agent — AWS Deployment"
echo "   Region  : $AWS_REGION"
echo "   Cluster : $ECS_CLUSTER"
echo ""

# ── Step 1: Docker image build & push ──
echo "📦 Building Docker image..."
docker build -t $IMAGE_NAME:latest .
docker tag $IMAGE_NAME:latest $DOCKER_USERNAME/$IMAGE_NAME:latest
docker push $DOCKER_USERNAME/$IMAGE_NAME:latest
echo "✅ Image pushed: $DOCKER_USERNAME/$IMAGE_NAME:latest"

# ── Step 2: CloudWatch Log Group ──
echo "📋 Creating CloudWatch log group..."
aws logs create-log-group \
    --log-group-name $LOG_GROUP \
    --region $AWS_REGION 2>/dev/null || echo "   Log group already exists."

# ── Step 3: Secrets Manager — store credentials ──
echo "🔐 Storing secrets in AWS Secrets Manager..."

store_secret() {
    local name=$1
    local value=$2
    aws secretsmanager create-secret \
        --name "birthday-agent/$name" \
        --secret-string "$value" \
        --region $AWS_REGION 2>/dev/null || \
    aws secretsmanager update-secret \
        --secret-id "birthday-agent/$name" \
        --secret-string "$value" \
        --region $AWS_REGION
    echo "   ✅ Secret stored: birthday-agent/$name"
}

# Load from .env
if [ -f ".env" ]; then
    source .env
    store_secret "USERNAME" "$USERNAME"
    store_secret "PASSWORD" "$PASSWORD"
    [ -n "$GITHUB_URL" ] && store_secret "GITHUB_URL" "$GITHUB_URL"
else
    echo "   ⚠️  .env not found — secrets not stored. Add manually in AWS Console."
fi

# ── Step 4: ECS Cluster ──
echo "🏗️  Creating ECS cluster..."
aws ecs create-cluster \
    --cluster-name $ECS_CLUSTER \
    --region $AWS_REGION 2>/dev/null || echo "   Cluster already exists."

# ── Step 5: Register Task Definition ──
echo "📋 Registering ECS task definition..."
TASK_DEF=$(cat deploy/aws/ecs-task-definition.json | \
    sed "s/YOUR_ACCOUNT_ID/$AWS_ACCOUNT_ID/g" | \
    sed "s/YOUR_DOCKERHUB_USERNAME/$DOCKER_USERNAME/g")

aws ecs register-task-definition \
    --cli-input-json "$TASK_DEF" \
    --region $AWS_REGION
echo "✅ Task definition registered."

# ── Step 6: Create or Update ECS Service ──
echo "⚙️  Creating/updating ECS service..."
SERVICE_EXISTS=$(aws ecs describe-services \
    --cluster $ECS_CLUSTER \
    --services $ECS_SERVICE \
    --region $AWS_REGION \
    --query 'services[0].status' \
    --output text 2>/dev/null || echo "MISSING")

if [ "$SERVICE_EXISTS" == "ACTIVE" ]; then
    aws ecs update-service \
        --cluster $ECS_CLUSTER \
        --service $ECS_SERVICE \
        --task-definition birthday-agent \
        --force-new-deployment \
        --region $AWS_REGION
    echo "✅ Service updated."
else
    aws ecs create-service \
        --cluster $ECS_CLUSTER \
        --service-name $ECS_SERVICE \
        --task-definition birthday-agent \
        --desired-count 1 \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[YOUR_SUBNET_ID],securityGroups=[YOUR_SG_ID],assignPublicIp=ENABLED}" \
        --region $AWS_REGION
    echo "✅ Service created."
fi

echo ""
echo "🎉 Deployment complete!"
echo "   Monitor: https://console.aws.amazon.com/ecs/home?region=$AWS_REGION#/clusters/$ECS_CLUSTER"
echo "   Logs   : https://console.aws.amazon.com/cloudwatch/home?region=$AWS_REGION#logsV2:log-groups/log-group/$LOG_GROUP"
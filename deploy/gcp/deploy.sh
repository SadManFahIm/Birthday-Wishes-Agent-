#!/bin/bash
# ══════════════════════════════════════════════
# deploy/gcp/deploy.sh
# GCP Cloud Run-এ Birthday Agent deploy করার script
#
# Requirements:
#   - gcloud CLI installed & configured (gcloud auth login)
#   - Docker installed
#
# Usage:
#   chmod +x deploy/gcp/deploy.sh
#   ./deploy/gcp/deploy.sh
# ══════════════════════════════════════════════

set -e

# ── Config ──
GCP_PROJECT="YOUR_GCP_PROJECT_ID"
GCP_REGION="us-central1"
DOCKER_USERNAME="YOUR_DOCKERHUB_USERNAME"
IMAGE_NAME="birthday-agent"
SERVICE_NAME="birthday-agent"
GCS_BUCKET="birthday-agent-data"

echo "🚀 Birthday Agent — GCP Deployment"
echo "   Project : $GCP_PROJECT"
echo "   Region  : $GCP_REGION"
echo ""

# ── Step 1: Set project ──
gcloud config set project $GCP_PROJECT

# ── Step 2: Enable required APIs ──
echo "🔧 Enabling GCP APIs..."
gcloud services enable \
    run.googleapis.com \
    secretmanager.googleapis.com \
    storage.googleapis.com \
    --quiet
echo "✅ APIs enabled."

# ── Step 3: Build & push image ──
echo "📦 Building and pushing Docker image..."
docker build -t $IMAGE_NAME:latest .
docker tag $IMAGE_NAME:latest $DOCKER_USERNAME/$IMAGE_NAME:latest
docker push $DOCKER_USERNAME/$IMAGE_NAME:latest
echo "✅ Image pushed."

# ── Step 4: GCS Bucket for persistent data ──
echo "🪣 Creating GCS bucket for persistent storage..."
gsutil mb -p $GCP_PROJECT -l $GCP_REGION gs://$GCS_BUCKET 2>/dev/null || \
    echo "   Bucket already exists."

# ── Step 5: Store secrets in Secret Manager ──
echo "🔐 Storing secrets in GCP Secret Manager..."

store_secret() {
    local name=$1
    local value=$2
    echo -n "$value" | gcloud secrets create $name \
        --data-file=- \
        --replication-policy="automatic" 2>/dev/null || \
    echo -n "$value" | gcloud secrets versions add $name --data-file=-
    echo "   ✅ Secret stored: $name"
}

if [ -f ".env" ]; then
    source .env
    store_secret "linkedin-username" "$USERNAME"
    store_secret "linkedin-password" "$PASSWORD"
    [ -n "$GITHUB_URL" ] && store_secret "github-url" "$GITHUB_URL"
else
    echo "   ⚠️  .env not found — add secrets manually in GCP Console."
fi

# ── Step 6: Deploy to Cloud Run ──
echo "☁️  Deploying to Cloud Run..."
YAML=$(cat deploy/gcp/cloudrun-service.yaml | \
    sed "s/YOUR_DOCKERHUB_USERNAME/$DOCKER_USERNAME/g" | \
    sed "s/YOUR_GCS_BUCKET_NAME/$GCS_BUCKET/g")

echo "$YAML" | gcloud run services replace - \
    --region $GCP_REGION \
    --quiet 2>/dev/null || \
gcloud run deploy $SERVICE_NAME \
    --image $DOCKER_USERNAME/$IMAGE_NAME:latest \
    --region $GCP_REGION \
    --platform managed \
    --no-allow-unauthenticated \
    --min-instances 1 \
    --max-instances 1 \
    --memory 1Gi \
    --cpu 1 \
    --no-cpu-throttling \
    --quiet

echo ""
echo "🎉 Deployment complete!"
echo "   Monitor: https://console.cloud.google.com/run/detail/$GCP_REGION/$SERVICE_NAME"
echo "   Logs   : https://console.cloud.google.com/logs/query?project=$GCP_PROJECT"
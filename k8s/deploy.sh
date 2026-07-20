#!/usr/bin/env bash
# k8s/deploy.sh — Deploy Birthday Wishes Agent to Kubernetes
set -euo pipefail

NAMESPACE="birthday-agent"
IMAGE_TAG="${IMAGE_TAG:-9.0}"

echo "🎂 Deploying Birthday Wishes Agent v${IMAGE_TAG} to Kubernetes..."
echo ""

# 1. Namespace
echo "→ Namespace..."
kubectl apply -f k8s/namespace.yaml

# 2. Config + Secrets
echo "→ ConfigMap & Secrets..."
kubectl apply -f k8s/configmap.yaml

echo ""
echo "⚠️  IMPORTANT: Update k8s/configmap.yaml with real credentials before deploying."
echo "   Or: kubectl create secret generic birthday-agent-secrets \\"
echo "       --from-env-file=.env -n ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -"
echo ""

# 3. Data layer
echo "→ PostgreSQL..."
kubectl apply -f k8s/postgres.yaml

echo "→ Redis..."
kubectl apply -f k8s/redis.yaml

echo "→ Waiting for data layer to be ready..."
kubectl rollout status statefulset/birthday-agent-postgres -n "${NAMESPACE}" --timeout=120s
kubectl rollout status deployment/birthday-agent-redis    -n "${NAMESPACE}" --timeout=60s

# 4. Run DB migration job
echo "→ Running PostgreSQL migration..."
kubectl run birthday-agent-migrate \
  --image="sadmanfahim/birthday-agent:${IMAGE_TAG}" \
  --restart=Never \
  --namespace="${NAMESPACE}" \
  --env-from=configmap/birthday-agent-config \
  --env-from=secret/birthday-agent-secrets \
  --command -- python postgres_migration.py migrate \
  2>/dev/null || true
kubectl wait --for=condition=complete job/birthday-agent-migrate \
  -n "${NAMESPACE}" --timeout=120s 2>/dev/null || true

# 5. Application layer
echo "→ FastAPI backend..."
kubectl apply -f k8s/api.yaml

echo "→ Queue worker..."
kubectl apply -f k8s/agent.yaml

echo "→ Next.js frontend..."
kubectl apply -f k8s/frontend.yaml

echo "→ Ingress..."
kubectl apply -f k8s/ingress.yaml

echo ""
echo "→ Waiting for deployments to roll out..."
kubectl rollout status deployment/birthday-agent-api           -n "${NAMESPACE}" --timeout=120s
kubectl rollout status deployment/birthday-agent-frontend      -n "${NAMESPACE}" --timeout=120s
kubectl rollout status deployment/birthday-agent-queue-worker  -n "${NAMESPACE}" --timeout=60s

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Services:"
kubectl get svc -n "${NAMESPACE}"
echo ""
echo "Pods:"
kubectl get pods -n "${NAMESPACE}"
echo ""
echo "Access:"
echo "  API docs : http://api.birthday-agent.local/docs"
echo "  Frontend : http://birthday-agent.local"
echo "  (Add to /etc/hosts or use kubectl port-forward)"
echo ""
echo "Port-forward (local dev):"
echo "  kubectl port-forward svc/birthday-agent-api      8000:8000 -n ${NAMESPACE}"
echo "  kubectl port-forward svc/birthday-agent-frontend 3000:3000 -n ${NAMESPACE}"

# Kubernetes Deployment — Birthday Wishes Agent v9.0

Deploy the full Birthday Wishes Agent stack to any Kubernetes cluster.

## Architecture

```
Ingress (nginx)
  ├── birthday-agent.local         → frontend (Next.js, port 3000)
  └── api.birthday-agent.local     → api (FastAPI, port 8000)

Deployments
  ├── birthday-agent-api           2 replicas, HPA (2-6 pods)
  ├── birthday-agent-frontend      1 replica
  └── birthday-agent-queue-worker  1 replica (Redis task consumer)

CronJob
  └── birthday-agent-worker        Daily at 08:00 UTC (main agent run)

StatefulSet
  └── birthday-agent-postgres      PostgreSQL 16 + 5Gi PVC

Deployment
  └── birthday-agent-redis         Redis 7 (128MB LRU)
```

## Quick Start

```bash
# 1. Update credentials
cp k8s/configmap.yaml k8s/configmap.local.yaml
# Edit k8s/configmap.local.yaml with real API keys

# 2. Deploy
chmod +x k8s/deploy.sh
./k8s/deploy.sh

# 3. Port-forward for local access
kubectl port-forward svc/birthday-agent-api      8000:8000 -n birthday-agent
kubectl port-forward svc/birthday-agent-frontend 3000:3000 -n birthday-agent
```

## Files

| File | Description |
|------|-------------|
| `namespace.yaml` | birthday-agent namespace |
| `configmap.yaml` | Non-sensitive config + secret template |
| `postgres.yaml` | PostgreSQL 16 StatefulSet + Service |
| `redis.yaml` | Redis 7 Deployment + Service |
| `api.yaml` | FastAPI Deployment + Service + HPA |
| `agent.yaml` | CronJob (daily run) + queue worker |
| `frontend.yaml` | Next.js Deployment + Service |
| `ingress.yaml` | nginx Ingress rules |
| `deploy.sh` | One-command deploy |
| `teardown.sh` | One-command teardown |

## Secrets

```bash
# Recommended: create from .env file
kubectl create secret generic birthday-agent-secrets \
  --from-env-file=.env \
  -n birthday-agent \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Scaling

```bash
# Manual scale
kubectl scale deployment birthday-agent-api --replicas=4 -n birthday-agent

# HPA auto-scales 2-6 pods on CPU > 70%
kubectl get hpa -n birthday-agent
```

## Monitoring

```bash
kubectl get pods    -n birthday-agent
kubectl get svc     -n birthday-agent
kubectl logs -f deploy/birthday-agent-api -n birthday-agent
kubectl logs -f deploy/birthday-agent-queue-worker -n birthday-agent
kubectl get cronjobs -n birthday-agent
```

Built by [SadManFahIm](https://github.com/SadManFahIm)

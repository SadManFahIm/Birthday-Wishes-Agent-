# ☁️ Cloud Deployment Guide

Birthday Agent কে local machine ছাড়াই **24/7 cloud-এ** run করার guide।

---

## 📁 Structure

```
deploy/
├── aws/
│   ├── deploy.sh               ← AWS one-command deploy
│   └── ecs-task-definition.json
└── gcp/
    ├── deploy.sh               ← GCP one-command deploy
    └── cloudrun-service.yaml
```

---

## 🟠 Option 1 — AWS (ECS Fargate)

### Prerequisites

- [AWS CLI](https://aws.amazon.com/cli/) installed
- `aws configure` দিয়ে credentials set করা
- Docker installed
- Docker Hub account

### Steps

**1. `deploy/aws/deploy.sh` এ তোমার values বসাও:**

```bash
AWS_ACCOUNT_ID="123456789012"        # AWS Console থেকে
DOCKER_USERNAME="your_dockerhub_id"  # Docker Hub username
```

**2. Run:**

```bash
chmod +x deploy/aws/deploy.sh
./deploy/aws/deploy.sh
```

এটা automatically করবে:

- Docker image build + push
- AWS Secrets Manager-এ credentials store
- CloudWatch log group তৈরি
- ECS Cluster + Task Definition + Service deploy

### Cost estimate

| Resource                    | Cost/month     |
| --------------------------- | -------------- |
| ECS Fargate (0.5 vCPU, 1GB) | ~$15           |
| EFS storage                 | ~$1            |
| CloudWatch logs             | ~$1            |
| **Total**                   | **~$17/month** |

---

## 🔵 Option 2 — GCP (Cloud Run)

### Prerequisites

- [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed
- `gcloud auth login` করা
- Docker installed

### Steps

**1. `deploy/gcp/deploy.sh` এ তোমার values বসাও:**

```bash
GCP_PROJECT="your-project-id"        # GCP Console থেকে
DOCKER_USERNAME="your_dockerhub_id"
```

**2. Run:**

```bash
chmod +x deploy/gcp/deploy.sh
./deploy/gcp/deploy.sh
```

এটা automatically করবে:

- Required GCP APIs enable
- Docker image build + push
- GCS bucket তৈরি (persistent storage)
- Secret Manager-এ credentials store
- Cloud Run service deploy (min 1 instance = 24/7)

### Cost estimate

| Resource                           | Cost/month     |
| ---------------------------------- | -------------- |
| Cloud Run (1 vCPU, 1GB, always-on) | ~$20           |
| GCS storage                        | ~$1            |
| Secret Manager                     | free tier      |
| **Total**                          | **~$21/month** |

---

## 🔐 Secrets Setup

`.env` file থেকে automatically secrets load হয়। Manual-এ করতে চাইলে:

**AWS:**

```bash
aws secretsmanager create-secret \
    --name "birthday-agent/USERNAME" \
    --secret-string "your_linkedin_email"
```

**GCP:**

```bash
echo -n "your_linkedin_email" | \
    gcloud secrets create linkedin-username --data-file=-
```

---

## 📊 Monitoring

**AWS CloudWatch:**

```
https://console.aws.amazon.com/cloudwatch → Log groups → /ecs/birthday-agent
```

**GCP Cloud Logging:**

```
https://console.cloud.google.com/logs → Filter: resource.type="cloud_run_revision"
```

---

## 💡 Tips

- **DRY_RUN = False** set করো production-এ
- Schedule time UTC-তে দিতে হবে (`SCHEDULE_HOUR = 3` = Bangladesh সকাল ৯টা)
- Multi-account secrets আলাদা আলাদা store করো

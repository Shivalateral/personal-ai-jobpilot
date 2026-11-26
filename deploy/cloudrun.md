# Google Cloud Run Deployment Guide

## 1. Prerequisites
- Google Cloud Project with Billing enabled
- `gcloud` CLI authenticated (`gcloud auth login && gcloud config set project YOUR_PROJECT_ID`)
- Enabled APIs:
  ```bash
  gcloud services enable run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    cloudscheduler.googleapis.com
  ```

## 2. Provision Cloud SQL (PostgreSQL) & Secret Manager
1. Create a Cloud SQL PostgreSQL 16 instance (`jobpilot-pg`) and database `jobpilot`.
2. Store sensitive values in Secret Manager (never commit secrets in source):
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" | \
     gcloud secrets create jobpilot-fernet-key --data-file=-

   printf "postgresql+psycopg2://jobpilot:PASSWORD@/jobpilot?host=/cloudsql/PROJECT:REGION:jobpilot-pg" | \
     gcloud secrets create jobpilot-database-url --data-file=-

   printf "YOUR_LLM_API_KEY" | gcloud secrets create jobpilot-llm-key --data-file=-
   printf "YOUR_SCHEDULER_TOKEN" | gcloud secrets create jobpilot-scheduler-token --data-file=-
   ```

## 3. Build & Deploy Services
1. Create an Artifact Registry repository:
   ```bash
   gcloud artifacts repositories create jobpilot --repository-format=docker --location=us-central1
   ```
2. Trigger Cloud Build:
   ```bash
   gcloud builds submit --config cloudbuild.yaml
   ```
3. Attach Cloud SQL and Secret Manager bindings to `jobpilot-backend`:
   ```bash
   gcloud run services update jobpilot-backend \
     --region=us-central1 \
     --add-cloudsql-instances=PROJECT:us-central1:jobpilot-pg \
     --set-secrets="DATABASE_URL=jobpilot-database-url:latest,RESUME_ENCRYPTION_KEY=jobpilot-fernet-key:latest,LLM_API_KEY=jobpilot-llm-key:latest,SCHEDULER_AUTH_TOKEN=jobpilot-scheduler-token:latest" \
     --set-env-vars="SCHEDULER_ENABLED=false,APP_ENV=production"
   ```
   *(Set `SCHEDULER_ENABLED=false` on Cloud Run so Google Cloud Scheduler drives daily runs instead of an in-container cron when scaling to zero.)*

4. Point `jobpilot-frontend` to the backend URL:
   ```bash
   BACKEND_URL=$(gcloud run services describe jobpilot-backend --region=us-central1 --format='value(status.url)')
   gcloud run services update jobpilot-frontend \
     --region=us-central1 \
     --set-env-vars="FRONTEND_API_URL=${BACKEND_URL}"
   ```

## 4. Configure Google Cloud Scheduler (Daily Autonomous Discovery)
Create a daily Cloud Scheduler job (08:00 UTC) calling `/api/v1/scheduler/run`:
```bash
gcloud scheduler jobs create http jobpilot-daily-discovery \
  --location=us-central1 \
  --schedule="0 8 * * *" \
  --time-zone="UTC" \
  --uri="${BACKEND_URL}/api/v1/scheduler/run" \
  --http-method=POST \
  --headers="Authorization=Bearer YOUR_SCHEDULER_TOKEN"
```

#!/bin/bash
# FinanzBro - Cloud Run Job Deployment
#
# Erstellt einen Cloud Run Job + Cloud Scheduler Trigger
# für die tägliche Portfolio-Analyse + Telegram-Report.
#
# Voraussetzungen:
#   1. gcloud CLI installiert und eingeloggt: gcloud auth login
#   2. GCP Projekt gesetzt: gcloud config set project DEIN-PROJEKT-ID
#   3. APIs aktiviert:
#      gcloud services enable run.googleapis.com cloudscheduler.googleapis.com artifactregistry.googleapis.com
#
# Verwendung:
#   chmod +x deploy_job.sh
#   ./deploy_job.sh

set -e

# ============ Konfiguration ============
JOB_NAME="finanzbro-daily"
REGION="europe-west1"
SCHEDULE="15 16 * * 1-5"  # Mo-Fr um 16:15 CET (tägliche Analyse)
SCHEDULE_WEEKLY="30 22 * * 5"  # Freitag 22:30 CET (Weekly Digest nach US-Börsenschluss)
TIMEZONE="Europe/Berlin"

# ============ Checks ============
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI nicht gefunden. Bitte installieren:"
    echo "   https://cloud.google.com/sdk/docs/install"
    exit 1
fi

PROJECT=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT" ]; then
    echo "❌ Kein GCP Projekt gesetzt. Bitte ausführen:"
    echo "   gcloud config set project DEIN-PROJEKT-ID"
    exit 1
fi

echo "🚀 Deploying FinanzBro Daily Job..."
echo "   Job:      $JOB_NAME"
echo "   Region:   $REGION"
echo "   Projekt:  $PROJECT"
echo "   Schedule: $SCHEDULE ($TIMEZONE)"
echo ""

# ============ APIs aktivieren ============
echo "📦 Aktiviere APIs..."
gcloud services enable \
    run.googleapis.com \
    cloudscheduler.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    --quiet

# ============ Artifact Registry Repo erstellen ============
REPO_NAME="finanzbro"
echo "📦 Erstelle Artifact Registry Repository..."
gcloud artifacts repositories create $REPO_NAME \
    --repository-format=docker \
    --location=$REGION \
    --quiet 2>/dev/null || echo "   (Repository existiert bereits)"

# ============ Docker Image bauen und pushen ============
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO_NAME}/${JOB_NAME}:latest"
echo "🐳 Baue Docker Image..."
gcloud builds submit \
    --tag "$IMAGE" \
    --dockerfile Dockerfile.job \
    --quiet

# ============ Cloud Run Job erstellen/aktualisieren ============
echo "☁️  Erstelle Cloud Run Job..."

# Lade .env Werte
source .env 2>/dev/null || true

gcloud run jobs create $JOB_NAME \
    --image "$IMAGE" \
    --region $REGION \
    --memory 1Gi \
    --cpu 1 \
    --task-timeout 600 \
    --max-retries 1 \
    --set-env-vars "ENVIRONMENT=production" \
    --set-env-vars "GCP_PROJECT_ID=${PROJECT}" \
    --set-env-vars "FMP_API_KEY=${FMP_API_KEY:-}" \
    --set-env-vars "FINNHUB_API_KEY=${FINNHUB_API_KEY:-}" \
    --set-env-vars "PARQET_ACCESS_TOKEN=${PARQET_ACCESS_TOKEN:-}" \
    --set-env-vars "PARQET_PORTFOLIO_ID=${PARQET_PORTFOLIO_ID:-}" \
    --set-env-vars "TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}" \
    --set-env-vars "TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID:-}" \
    --set-env-vars "GEMINI_API_KEY=${GEMINI_API_KEY:-}" \
    --quiet 2>/dev/null || \
gcloud run jobs update $JOB_NAME \
    --image "$IMAGE" \
    --region $REGION \
    --memory 1Gi \
    --cpu 1 \
    --task-timeout 600 \
    --max-retries 1 \
    --set-env-vars "ENVIRONMENT=production" \
    --set-env-vars "GCP_PROJECT_ID=${PROJECT}" \
    --set-env-vars "FMP_API_KEY=${FMP_API_KEY:-}" \
    --set-env-vars "FINNHUB_API_KEY=${FINNHUB_API_KEY:-}" \
    --set-env-vars "PARQET_ACCESS_TOKEN=${PARQET_ACCESS_TOKEN:-}" \
    --set-env-vars "PARQET_PORTFOLIO_ID=${PARQET_PORTFOLIO_ID:-}" \
    --set-env-vars "TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}" \
    --set-env-vars "TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID:-}" \
    --set-env-vars "GEMINI_API_KEY=${GEMINI_API_KEY:-}" \
    --quiet

# ============ Cloud Scheduler: Daily (Mo-Fr) ============
echo "⏰ Erstelle Cloud Scheduler (Daily)..."

# Service Account für Scheduler
SA_EMAIL="${PROJECT}@appspot.gserviceaccount.com"

gcloud scheduler jobs create http "${JOB_NAME}-trigger" \
    --location $REGION \
    --schedule "$SCHEDULE" \
    --time-zone "$TIMEZONE" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${JOB_NAME}:run" \
    --http-method POST \
    --oauth-service-account-email "$SA_EMAIL" \
    --quiet 2>/dev/null || \
gcloud scheduler jobs update http "${JOB_NAME}-trigger" \
    --location $REGION \
    --schedule "$SCHEDULE" \
    --time-zone "$TIMEZONE" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${JOB_NAME}:run" \
    --http-method POST \
    --oauth-service-account-email "$SA_EMAIL" \
    --quiet

# ============ Cloud Scheduler: Weekly Digest (Fr 18:30) ============
echo "⏰ Erstelle Cloud Scheduler (Weekly Digest)..."

gcloud scheduler jobs create http "${JOB_NAME}-weekly" \
    --location $REGION \
    --schedule "$SCHEDULE_WEEKLY" \
    --time-zone "$TIMEZONE" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${JOB_NAME}:run" \
    --http-method POST \
    --oauth-service-account-email "$SA_EMAIL" \
    --quiet 2>/dev/null || \
gcloud scheduler jobs update http "${JOB_NAME}-weekly" \
    --location $REGION \
    --schedule "$SCHEDULE_WEEKLY" \
    --time-zone "$TIMEZONE" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${JOB_NAME}:run" \
    --http-method POST \
    --oauth-service-account-email "$SA_EMAIL" \
    --quiet

echo ""
echo "✅ Deployment erfolgreich!"
echo ""
echo "📋 Zusammenfassung:"
echo "   Job:       $JOB_NAME"
echo "   Image:     $IMAGE"
echo "   Daily:     Mo-Fr 16:15 CET (Analyse + Telegram-Report)"
echo "   Weekly:    Fr 22:30 CET (Weekly Digest nach US-Börsenschluss)"
echo ""
echo "💡 Manuell ausführen:"
echo "   gcloud run jobs execute $JOB_NAME --region $REGION"
echo ""
echo "📊 Logs ansehen:"
echo "   gcloud run jobs executions list --job $JOB_NAME --region $REGION"
echo "   gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=$JOB_NAME' --limit 50"

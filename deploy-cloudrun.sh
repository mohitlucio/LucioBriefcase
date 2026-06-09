#!/usr/bin/env bash
set -euo pipefail

# Deploy LucioBriefcase to Google Cloud Run (100% managed, no VPS needed)
# Free tier: 2M requests/month, enough for your use case

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  LucioBriefcase → Google Cloud Run (Serverless)               ║"
echo "║  No VPS setup needed. Just push & deploy.                     ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &>/dev/null; then
    echo "Installing Google Cloud CLI..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        curl https://sdk.cloud.google.com | bash
        exec -l $SHELL
    else
        # Linux
        echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
        curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
        sudo apt-get update && sudo apt-get install -y google-cloud-cli
    fi
fi

echo ""
read -p "Enter your Google Cloud Project ID (create one at https://console.cloud.google.com): " PROJECT_ID
read -p "Enter desired app name (e.g., luciobriefcase): " APP_NAME

if [[ -z "$PROJECT_ID" ]] || [[ -z "$APP_NAME" ]]; then
    echo "❌ Both fields required"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Deploying to Cloud Run..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Authenticate
echo "Step 1: Authenticating with Google Cloud..."
gcloud auth login

# Set project
gcloud config set project "$PROJECT_ID"

# Enable required APIs
echo "Step 2: Enabling Cloud Run API..."
gcloud services enable run.googleapis.com artifactregistry.googleapis.com

# Build and deploy
echo "Step 3: Building Docker image and deploying to Cloud Run..."
gcloud run deploy "$APP_NAME" \
    --source . \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --memory 4Gi \
    --cpu 2 \
    --timeout 3600 \
    --max-instances 10 \
    --set-env-vars="CLOUD=1,AUTO_SCRAPE_ON_START=1,DOWNLOAD_DIR=/workspace/data" \
    --port 10000

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployment Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Your app is now live!"
echo ""
echo "Get your URL:"
gcloud run services describe "$APP_NAME" --region us-central1 --format='value(status.url)'
echo ""
echo "View logs:"
echo "  gcloud run services logs read $APP_NAME --region us-central1 -f"
echo ""
echo "Updates: Just commit & push to main — re-run this script to redeploy"
echo ""

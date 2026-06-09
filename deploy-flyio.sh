#!/usr/bin/env bash
set -euo pipefail

# Deploy LucioBriefcase to Fly.io (Simple containerized hosting)
# Free tier: 3 shared-cpu-1x 256MB VMs

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  LucioBriefcase → Fly.io (Serverless Containers)              ║"
echo "║  Free tier included. HTTPS auto-provisioned.                  ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check if flyctl is installed
if ! command -v flyctl &>/dev/null; then
    echo "Installing Fly CLI..."
    curl -L https://fly.io/install.sh | sh
    export PATH="$HOME/.fly/bin:$PATH"
fi

echo ""
echo "Step 1: Logging in to Fly..."
flyctl auth login

echo ""
echo "Step 2: Deploying your app..."
flyctl launch --no-deploy --copy-existing-wg=false --generate-name

echo ""
echo "Step 3: Creating persistent volume for data..."
flyctl volumes create repositories_data --size 10 --region iad

echo ""
echo "Step 4: Deploying to production..."
flyctl deploy

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployment Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Your app is live at:"
flyctl info --format='{{ .Hostname }}'
echo ""
echo "View logs:"
echo "  flyctl logs -f"
echo ""
echo "Update & redeploy:"
echo "  git commit && git push"
echo "  flyctl deploy"
echo ""

#!/usr/bin/env bash
set -euo pipefail

# LucioBriefcase — Complete VPS Auto-Deploy
# Usage: ./deploy-complete.sh

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     LucioBriefcase Complete VPS Deployment                    ║"
echo "║     This will deploy your app to a live VPS with HTTPS        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Collect VPS details
read -p "VPS IP Address (e.g., 123.45.67.89): " VPS_IP
read -p "Your Domain (e.g., briefcase.example.com): " DOMAIN
read -p "SSH User (usually 'root' for new VPS): " SSH_USER
read -sp "SSH Password (will not be echoed): " SSH_PASS
echo ""

# Validate inputs
if [[ -z "$VPS_IP" ]] || [[ -z "$DOMAIN" ]] || [[ -z "$SSH_USER" ]]; then
    echo "❌ All fields required. Exiting."
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Deploying to: $DOMAIN ($VPS_IP)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# SSH command helper using sshpass (install if needed)
if ! command -v sshpass &> /dev/null; then
    echo "Installing sshpass for password-based SSH..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install sshpass
    else
        sudo apt-get update && sudo apt-get install -y sshpass
    fi
fi

SSH_CMD="sshpass -p '$SSH_PASS' ssh -o StrictHostKeyChecking=no $SSH_USER@$VPS_IP"

echo "Step 1: Connecting to VPS and installing Docker..."
$SSH_CMD << 'DEPLOY_SCRIPT'
set -e
echo "✓ Connected to VPS"

# Update system
apt-get update -qq
echo "✓ System updated"

# Install Docker
if ! command -v docker &>/dev/null; then
    apt-get install -y -qq docker.io docker-compose-plugin git curl
    systemctl enable --now docker
    echo "✓ Docker installed"
else
    echo "✓ Docker already installed"
fi

# Stop any existing container
docker compose -f /opt/luciobriefcase/docker-compose.prod.yml down 2>/dev/null || true

DEPLOY_SCRIPT

echo ""
echo "Step 2: Cloning repository..."
$SSH_CMD << 'DEPLOY_SCRIPT'
rm -rf /opt/luciobriefcase
git clone https://github.com/mohitlucio/LucioBriefcase.git /opt/luciobriefcase
cd /opt/luciobriefcase
chmod +x ops/deploy_vps.sh
echo "✓ Repository cloned"

DEPLOY_SCRIPT

echo ""
echo "Step 3: Deploying application with Docker..."
DOMAIN="$DOMAIN" $SSH_CMD "cd /opt/luciobriefcase && DOMAIN=$DOMAIN ./ops/deploy_vps.sh $DOMAIN"

echo ""
echo "✓ Deployment complete!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Your app is deploying..."
echo ""
echo "Next steps:"
echo ""
echo "1. Make sure DNS A record points to $VPS_IP"
echo "   (Registrar → DNS Settings → A Record → $DOMAIN → $VPS_IP)"
echo ""
echo "2. Wait 2-3 minutes for deployment to complete"
echo ""
echo "3. Open in browser:"
echo "   → https://$DOMAIN"
echo ""
echo "Verify deployment:"
echo "   → curl https://$DOMAIN/health"
echo ""
echo "Check logs:"
echo "   → $SSH_CMD 'docker compose -f /opt/luciobriefcase/docker-compose.prod.yml logs -f'"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

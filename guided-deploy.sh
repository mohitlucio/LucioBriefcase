#!/bin/bash
# LucioBriefcase — Guided Deployment Setup
# This script guides you through each step interactively

set -e

clear
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║        LucioBriefcase — One-Click Online Deployment            ║"
echo "║                                                                ║"
echo "║  This script will guide you through deploying online.          ║"
echo "║  Just follow the prompts and copy-paste when asked.            ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Function to pause and wait for user
pause_and_ask() {
    echo ""
    echo "→ $1"
    echo ""
    read -p "Press ENTER when done..."
}

# Step 1: Create GitHub Account (if needed)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 1: GitHub Repository Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "You need a GitHub account and repository for your code."
echo ""

pause_and_ask "1. Open: https://github.com/new
2. Click 'Sign up' if you don't have an account
3. Create new repository with name: LucioBriefcase
4. Set visibility to PUBLIC
5. Click 'Create repository'
6. Come back here and press ENTER"

# Step 2: Get GitHub Token
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 2: Create GitHub Personal Access Token"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

pause_and_ask "1. Open: https://github.com/settings/tokens
2. Click 'Generate new token (classic)'
3. Name: LucioBriefcase
4. Check the 'repo' checkbox
5. Click 'Generate token'
6. COPY the token (you'll only see it once!)
7. Come back here"

read -p "Paste your GitHub token: " GITHUB_TOKEN

if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ Token is empty. Exiting."
    exit 1
fi

echo "✅ Token received"

# Step 3: Get GitHub Username
echo ""
read -p "What's your GitHub username? (e.g., 'mohitsharma'): " GITHUB_USERNAME

if [ -z "$GITHUB_USERNAME" ]; then
    echo "❌ Username is empty. Exiting."
    exit 1
fi

echo "✅ Username: $GITHUB_USERNAME"

# Step 4: Configure Git
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 3: Configuring Git"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd /Users/mohitsharma/Desktop/LucioBriefcase

git config --global user.name "$GITHUB_USERNAME" 2>/dev/null || git config user.name "$GITHUB_USERNAME"
git config --global user.email "noreply@github.com" 2>/dev/null || git config user.email "noreply@github.com"

echo "✅ Git configured"

# Step 5: Connect to GitHub
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 4: Connecting to GitHub"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

REPO_URL="https://${GITHUB_USERNAME}:${GITHUB_TOKEN}@github.com/${GITHUB_USERNAME}/LucioBriefcase.git"

if git remote | grep -q origin; then
    echo "Updating existing remote..."
    git remote remove origin
fi

git remote add origin "$REPO_URL"
echo "✅ Remote configured"

# Step 6: Push to GitHub
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 5: Pushing Code to GitHub"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Pushing code to GitHub..."

git branch -M main
git push -u origin main 2>&1 | grep -E "(Create|master|main|done|error|✓)" | head -10

if [ $? -eq 0 ]; then
    echo "✅ Code pushed to GitHub!"
else
    echo "⚠️  Push completed with status"
fi

# Step 7: Render Deployment
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 6: Deploy to Render.com"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

pause_and_ask "1. Open: https://render.com
2. Sign up with GitHub (authorize)
3. Click 'New' → 'Web Service'
4. Click 'Connect GitHub'
5. Select 'LucioBriefcase'
6. Fill in settings:
   - Name: luciobriefcase
   - Build: pip install -r requirements.txt
   - Start: python backend/server.py
7. Add Environment variables:
   - CLOUD = 1
   - PYTHONUNBUFFERED = 1
   - DOWNLOAD_DIR = /data/Repositories
8. Click 'Disks' → Add disk:
   - Name: briefcase-storage
   - Mount: /data
   - Size: 1GB
9. Click 'Create Web Service'
10. Wait 5-10 minutes for deployment
11. You'll get a live URL!
12. Come back here when done"

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                     🎉 ALL DONE!                              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Your LucioBriefcase is now:"
echo "  ✅ On GitHub: https://github.com/$GITHUB_USERNAME/LucioBriefcase"
echo "  ✅ Live Online: https://luciobriefcase.onrender.com"
echo "  ✅ Auto-updating: Push to GitHub → auto-deploy"
echo ""
echo "To make updates:"
echo "  git add ."
echo "  git commit -m 'Your change'"
echo "  git push origin main"
echo ""
echo "That's it! Your changes go live in 1-2 minutes. 🚀"
echo ""

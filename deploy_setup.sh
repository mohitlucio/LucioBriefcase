#!/bin/bash
# Quick Deploy to Render.com
# This script helps you set up your LucioBriefcase for online deployment

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         LucioBriefcase — Online Deployment Setup               ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo "❌ Git is not installed. Please install Git first."
    echo "   → https://git-scm.com/download"
    exit 1
fi

# Initialize git repo if needed
if [ ! -d ".git" ]; then
    echo "📝 Initializing Git repository..."
    git init
    git add .
    git commit -m "Initial commit: LucioBriefcase ready for deployment"
    git branch -M main
    echo "✅ Git repository initialized"
else
    echo "✅ Git repository already exists"
fi

# Display next steps
echo ""
echo "📋 NEXT STEPS:"
echo ""
echo "1️⃣  Create a GitHub repository:"
echo "   • Go to https://github.com/new"
echo "   • Name: LucioBriefcase"
echo "   • Create repository"
echo ""
echo "2️⃣  Connect your local repo to GitHub:"
echo "   git remote add origin https://github.com/YOUR_USERNAME/LucioBriefcase.git"
echo "   git push -u origin main"
echo ""
echo "3️⃣  Deploy to Render:"
echo "   • Go to https://render.com"
echo "   • Sign up (use GitHub for faster setup)"
echo "   • Click 'New' → 'Web Service'"
echo "   • Connect GitHub and select this repository"
echo "   • Fill in the form (see DEPLOYMENT.md for details)"
echo "   • Deploy!"
echo ""
echo "4️⃣  Set up automatic updates:"
echo "   • Get API token from: https://render.com/account/api-tokens"
echo "   • Add GitHub secrets (see DEPLOYMENT.md)"
echo "   • From now on, just: git push → auto-deploys!"
echo ""
echo "📖 For detailed instructions, see: DEPLOYMENT.md"
echo ""

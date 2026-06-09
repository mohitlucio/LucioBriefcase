# LucioBriefcase — Online Deployment Guide

## Quick Overview

Your LucioBriefcase project is now configured for online deployment! Follow these steps to deploy to **Render.com** (free tier available) with automatic updates via GitHub Actions.

---

## Step 1: Set Up GitHub Repository

### 1a. Create a new GitHub repository

1. Go to [github.com/new](https://github.com/new)
2. Repository name: `LucioBriefcase`
3. Description: `93-Source Regulatory Document Briefcase`
4. Choose **Public** (so users can access)
5. Click **Create repository**

### 1b. Initialize Git and push code

```bash
cd ~/Desktop/LucioBriefcase
git init
git add .
git commit -m "Initial commit: LucioBriefcase ready for deployment"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/LucioBriefcase.git
git push -u origin main
```

**Replace `YOUR_USERNAME` with your GitHub username**

---

## Step 2: Deploy to Render.com

### 2a. Create Render account

1. Go to [render.com](https://render.com)
2. Click **Sign up** and create account (use GitHub for faster setup)
3. Complete onboarding

### 2b. Connect GitHub and create service

1. In Render dashboard, click **New** → **Web Service**
2. Click **Connect GitHub**
3. Select `LucioBriefcase` repository
4. Fill in details:
   - **Name**: `luciobriefcase`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python backend/server.py`
   - **Instance Type**: `Free` (for testing) or `Starter` (for production)

### 2c. Set environment variables

1. Scroll to **Environment** section
2. Add these variables:
   - `CLOUD` = `1`
   - `PYTHONUNBUFFERED` = `1`

### 2d. Add persistent storage (for downloaded files)

1. Scroll to **Disks** section
2. Click **Add Disk**:
   - **Name**: `briefcase-storage`
   - **Mount Path**: `/data`
   - **Size**: `10 GB` (free tier gets 1GB)

3. Update `DOWNLOAD_DIR` environment variable:
   - Key: `DOWNLOAD_DIR`
   - Value: `/data/Repositories`

### 2e. Deploy

1. Click **Create Web Service**
2. Render will build and deploy automatically (~5-10 minutes)
3. Once live, you'll get a URL like: `https://luciobriefcase.onrender.com`

**Your app is now live!** 🎉

---

## Step 3: Set Up Automatic Updates via GitHub Actions

The `.github/workflows/deploy.yml` file is already configured. Now we just need to add deployment secrets.

### 3a. Get Render API Token

1. In Render dashboard, click your **profile icon** (top right)
2. Go to **Account Settings** → **API Tokens**
3. Click **Create API Token**
4. Copy the token (save it somewhere safe)

### 3b. Get Service ID

1. Go to your web service in Render
2. In the URL, find the ID: `https://dashboard.render.com/web/srv-XXXXXXXXX...`
3. Copy `srv-XXXXXXXXX` (the Service ID)

### 3c. Add GitHub Secrets

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** and add:

   **Secret 1:**
   - Name: `RENDER_API_TOKEN`
   - Value: (paste your Render API token)

   **Secret 2:**
   - Name: `RENDER_SERVICE_ID`
   - Value: (paste your Render Service ID like `srv-XXXXXXXXX`)

4. Click **Add secret** for each

---

## How to Make Updates

Now updates are automatic! Here's the workflow:

### To push an update:

```bash
cd ~/Desktop/LucioBriefcase
# Make your changes to any files
git add .
git commit -m "Update: [describe your change]"
git push origin main
```

### What happens next:

1. GitHub Actions workflow runs automatically
2. Your changes are deployed to Render.com
3. Within 1-2 minutes, your live site updates
4. Users see the new version at `https://luciobriefcase.onrender.com`

---

## File Structure on Cloud

```
luciobriefcase.onrender.com
├── /                           → Frontend (index.html)
├── /health                     → Health check endpoint
├── /api/status                 → Source status
├── /api/documents              → Documents API
├── /api/unified                → Unified search API
├── /api/download               → Download endpoint
└── /data/Repositories/         → Persistent storage for PDFs
    ├── RHP/
    ├── DRHP/
    ├── BSE_Placement/
    └── ... (all other sources)
```

---

## Useful Commands

### Check deployment logs

```bash
# In Render dashboard, click your service → Logs
# or use Render CLI:
render logs luciobriefcase
```

### Monitor updates

```bash
# Watch your repo's Actions tab:
# https://github.com/YOUR_USERNAME/LucioBriefcase/actions
```

### Manually trigger redeploy

In Render dashboard:
1. Click your web service
2. Click **Manual Deploy** → **Deploy latest commit**

---

## Troubleshooting

### Site shows 502 Bad Gateway

1. Check logs in Render dashboard (Logs tab)
2. Ensure all environment variables are set correctly
3. Click **Manual Deploy** to retry

### Downloads not persisting

1. Check if disk is mounted at `/data`
2. In server.py, ensure `DOWNLOAD_DIR=/data/Repositories`
3. Check disk usage in Render dashboard

### Scrapers too slow

- Render's free tier has limited CPU
- Upgrade to **Starter** instance for better performance
- Consider reducing update frequency or splitting sources

---

## Advanced: Custom Domain

To use your own domain (e.g., `briefcase.yourdomain.com`):

1. In Render dashboard, click your service
2. Go to **Settings** → **Custom Domain**
3. Add your domain
4. Update your domain DNS to point to Render
5. (Render provides DNS records in the dialog)

---

## Advanced: Environment-Specific Deployment

To deploy to both staging and production:

1. Create two Render services from the same repo
2. Use GitHub branches: `main` → production, `staging` → staging
3. Deploy to Render by branch in `.github/workflows/deploy.yml`

---

## Summary

✅ **Your app is live!**
✅ **Automatic updates via GitHub**
✅ **Persistent storage for documents**
✅ **Free tier available**
✅ **Easy to scale up**

**Share your live URL:** `https://luciobriefcase.onrender.com`

Users can now access LucioBriefcase without installing anything locally!

---

## Support

- **Render Docs**: https://render.com/docs
- **GitHub Actions**: https://docs.github.com/actions
- **Python Deployment**: https://render.com/docs/python-tips

For questions about your specific setup, check Render's dashboard logs or GitHub Actions logs.

# Railway.app Deployment Guide

## Quick Start (5 minutes)

### Step 1: Create Railway Account
1. Go to **https://railway.app**
2. Click **Start Free**
3. Sign in with **GitHub** (use your account)
4. Authorize Railway

### Step 2: Create New Project
1. Click **+ New Project**
2. Select **Deploy from GitHub repo**
3. Select **mohitlucio/LucioBriefcase**
4. Click **Deploy**

### Step 3: Configure Environment
Railway will auto-detect your Python app. Just add environment variables:

1. In Railway dashboard, click your project
2. Click **Variables** tab
3. Add:
   ```
   CLOUD=1
   PORT=8000
   PYTHONUNBUFFERED=1
   DOWNLOAD_DIR=/var/data/Repositories
   ```

### Step 4: Add Storage (Optional)
1. Click **+ Add Plugin**
2. Select **PostgreSQL** or **Disk** (if available)
3. Mount at `/var/data`

### Step 5: Deploy
Click **Deploy** → Wait 2-3 minutes

Your site will be live at the Railway-assigned domain! 🎉

---

## Environment Variables Reference

| Variable | Value | Purpose |
|----------|-------|---------|
| `CLOUD` | `1` | Enable cloud mode |
| `PORT` | `8000` | Web server port |
| `PYTHONUNBUFFERED` | `1` | Real-time logs |
| `DOWNLOAD_DIR` | `/var/data/Repositories` | Storage location |

---

## Auto-Updates (After Initial Deploy)

Just push to GitHub:
```bash
git add .
git commit -m "Your change"
git push origin main
```

Railway automatically redeploys in 1-2 minutes! 🚀

---

## Troubleshooting

**Site not loading?**
- Check Railway dashboard logs
- Verify environment variables are set
- Make sure PORT is 8000 or auto-assigned

**Need more resources?**
- Upgrade to paid plan ($5+/month)
- Get more CPU and memory

---

## Support

- Railway Docs: https://docs.railway.app
- Python Deployment: https://docs.railway.app/guides/runtimes#python

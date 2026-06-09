# LucioBriefcase Deploy Quick Reference

## 🚀 Deploy in 5 Steps (10 minutes)

### Step 1: GitHub Setup
```bash
cd ~/Desktop/LucioBriefcase
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/LucioBriefcase.git
git push -u origin main
```
> Go to https://github.com/new first, create repo, then run the above

### Step 2: Render Account
- Go to https://render.com
- Sign up with GitHub
- Verify email

### Step 3: Deploy Service
1. In Render dashboard: **New** → **Web Service**
2. **Connect GitHub** → Select `LucioBriefcase` → **Connect**
3. Fill the form:
   - **Name**: `luciobriefcase`
   - **Environment**: `Python 3`
   - **Build Cmd**: `pip install -r requirements.txt`
   - **Start Cmd**: `python backend/server.py`
4. **Environment** tab:
   - `CLOUD` = `1`
   - `PYTHONUNBUFFERED` = `1`
   - `DOWNLOAD_DIR` = `/data/Repositories`
5. **Disks** tab → Add Disk: Name=`briefcase-storage`, Mount=`/data`, Size=`1GB`
6. Click **Create Web Service**

> Wait 5-10 minutes. You'll get a live URL!

### Step 4: Auto-Deploy Setup
1. Render: **Account** (top right) → **API Tokens** → Create token, copy it
2. Render: Your service → Copy the Service ID from the URL
3. GitHub: **Settings** → **Secrets and variables** → **Actions** → **New**:
   - Name: `RENDER_API_TOKEN` → paste token
   - Name: `RENDER_SERVICE_ID` → paste service ID

### Step 5: Push Updates
```bash
# Make changes to any files
git add .
git commit -m "Update: fixed X feature"
git push origin main
```

✅ **Done!** Site auto-deploys in 1-2 minutes.

---

## 📝 Quick URLs

| What | Where |
|------|-------|
| Live site | `https://luciobriefcase.onrender.com` |
| Render dashboard | https://dashboard.render.com |
| GitHub repo | https://github.com/YOUR_USERNAME/LucioBriefcase |
| GitHub Actions | https://github.com/YOUR_USERNAME/LucioBriefcase/actions |
| Deployment guide | [DEPLOYMENT.md](DEPLOYMENT.md) |

---

## 🔧 Common Tasks

### Check if live
```
curl https://luciobriefcase.onrender.com/health
```

### View logs
Go to Render dashboard → your service → **Logs** tab

### Manual redeploy
Render dashboard → your service → **Manual Deploy** → **Deploy latest**

### Update settings
Render dashboard → your service → **Settings** → edit and save

---

## 💡 Troubleshooting

| Issue | Fix |
|-------|-----|
| Site shows 502 | Check Logs in Render; click Manual Deploy |
| Old version showing | Check GitHub Actions completed; wait 2 min |
| Downloads not saving | Check DOWNLOAD_DIR=/data/Repositories in env vars |
| Very slow | Free tier is limited; upgrade to Starter for speed |

---

## 🎯 What You Get

✅ Site accessible from anywhere
✅ Users see live regulatory documents
✅ PDFs persist in cloud storage  
✅ One-command updates (`git push`)
✅ Free tier (1GB storage, limited CPU)
✅ Easy upgrade path

---

## 📚 More Help

- Full guide: [DEPLOYMENT.md](DEPLOYMENT.md)
- Render docs: https://render.com/docs
- GitHub Actions: https://docs.github.com/actions

**Questions?** Check Render logs or GitHub Actions logs for error details.

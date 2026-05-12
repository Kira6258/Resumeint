# Resumeint — Deployment & API Key Guide

## 🔑 API Keys You Need

### 1. Google Gemini API Key (REQUIRED — FREE)
> **Used for:** Generating project roadmaps and AI code reviews

**How to get it:**
1. Go to → https://aistudio.google.com/app/apikey
2. Sign in with your Google account
3. Click **"Create API Key"**
4. Copy the key (starts with `AIza...`)

**Add to `.env`:**
```
GEMINI_API_KEY=AIzaSy...
```

---

### 2. Google OAuth Credentials (REQUIRED for Google Login)
> **Used for:** "Sign in with Google" button

**How to get it:**
1. Go to → https://console.cloud.google.com/
2. Create a new project (or use existing)
3. Go to **APIs & Services → OAuth consent screen** → configure as External
4. Go to **APIs & Services → Credentials** → Create **OAuth 2.0 Client ID**
5. Application type: **Web application**
6. Add Authorized redirect URIs:
   - Dev: `http://127.0.0.1:8000/auth/google/callback`
   - Prod: `https://yourdomain.com/auth/google/callback`
7. Copy Client ID and Client Secret

**Add to `.env`:**
```
GOOGLE_CLIENT_ID=90754242797-xxxxxxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxx
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/auth/google/callback
```

---

### 3. Razorpay Keys (REQUIRED for Payments)
> **Used for:** Pro plan subscriptions (₹50/month or ₹550/year)

**How to get it:**
1. Go to → https://dashboard.razorpay.com/
2. Sign up for a free account
3. Go to **Settings → API Keys** → Generate Test Key
4. Copy Key ID (starts with `rzp_test_...`) and Key Secret

**Add to `.env`:**
```
RAZORPAY_KEY_ID=rzp_test_XXXXXXXXXXXX
RAZORPAY_KEY_SECRET=XXXXXXXXXXXXXXXXXXXXXX
```

> ⚠️ Use `rzp_test_` keys for development. Switch to `rzp_live_` for production.

---

### 4. GitHub Personal Access Token (OPTIONAL — for GitHub Sync)
> **Used for:** "Sync to GitHub" feature in project view

**How to get it:**
1. Go to → https://github.com/settings/tokens
2. Click **Generate new token (classic)**
3. Select scopes: `repo` (full control of private repositories)
4. Copy the token (starts with `ghp_...`)

**Add to `.env`:**
```
GITHUB_TOKEN=ghp_XXXXXXXXXXXXXXXXXXXXXX
```

---

### 5. Gmail App Password (REQUIRED for Password Reset Emails)
> **Used for:** Sending forgot-password reset links

**Your current email:** `resumeint@gmail.com`  
The app password is already configured. If it stops working:

1. Go to your Google Account → Security
2. Enable 2-Step Verification (required)
3. Go to → https://myaccount.google.com/apppasswords
4. Create an app password for "Mail"
5. Copy the 16-character password (no spaces)

**Add to `.env`:**
```
MAIL_USERNAME=resumeint@gmail.com
MAIL_PASSWORD=xxxx xxxx xxxx xxxx  (without spaces)
MAIL_FROM=resumeint@gmail.com
MAIL_PORT=587
MAIL_SERVER=smtp.gmail.com
```

---

## 🚀 Production Deployment Checklist

Before going live, add these to your production `.env`:

```env
# Change to production
ENV=production

# Your live domain
BASE_URL=https://yourdomain.com
ALLOWED_ORIGINS=https://yourdomain.com

# Update Google redirect URI
GOOGLE_REDIRECT_URI=https://yourdomain.com/auth/google/callback

# Switch to live Razorpay keys
RAZORPAY_KEY_ID=rzp_live_XXXXXXXXXXXX
RAZORPAY_KEY_SECRET=XXXXXXXXXXXXXXXXXXXXXX
```

## 🏃 Running Locally

```bash
# First time only
python setup.py       # Configures .env

# Start the app
python run.py         # Runs on http://127.0.0.1:8000
```

## 🔍 Verify Everything Works

```bash
python doctor.py      # Checks Gemini API key, DB, and Razorpay
```

# Google OAuth 2.0 Setup Guide

## Prerequisites
- A Google account
- Access to [Google Cloud Console](https://console.cloud.google.com/)

## Steps

### 1. Create a Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** → **New Project**
3. Name it `EcoTracker` and click **Create**

### 2. Enable the OAuth API
1. In the left sidebar, go to **APIs & Services** → **Library**
2. Search for **"Google+ API"** or **"Google People API"** and enable it
3. (Optional) Also enable **"Gmail API"** if you plan to use Gmail features

### 3. Configure the OAuth Consent Screen
1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **External** and click **Create**
3. Fill in:
   - **App name**: `EcoTracker`
   - **User support email**: Your email
   - **Developer contact info**: Your email
4. Click **Save and Continue**
5. On Scopes page: Add `email`, `profile`, `openid`
6. Click **Save and Continue** through the remaining steps

### 4. Create OAuth 2.0 Credentials
1. Go to **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** → **OAuth 2.0 Client ID**
3. Application type: **Web application**
4. Name: `EcoTracker Web`
5. **Authorized redirect URIs** — add ALL of these:
   - `http://localhost:5000/auth/google/callback` (local development)
   - `https://your-app-name.onrender.com/auth/google/callback` (production)
6. Click **Create**

### 5. Copy Your Credentials
You'll see a dialog with:
- **Client ID**: `xxxxxxxxxxxx.apps.googleusercontent.com`
- **Client Secret**: `GOCSPX-xxxxxxxxxxxx`

### 6. Add to Your `.env` File
```env
GOOGLE_CLIENT_ID=xxxxxxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxx
```

### 7. Add to Render (Production)
1. Go to your Render dashboard → your web service
2. **Environment** tab → Add the same two variables

## Testing
1. Start the app: `python app.py`
2. Open `http://localhost:5000`
3. Click **"Sign in with Google"**
4. You should be redirected to Google's consent screen
5. After approving, you're redirected back and logged in

## Dev Mode (Without Google OAuth)
If `GOOGLE_CLIENT_ID` is empty in `.env`, the app automatically enables
**Dev Mode Login** — a simple name-based login form for local development.
No Google account required.

## Troubleshooting
- **"Error 400: redirect_uri_mismatch"**: Make sure the redirect URI in Google Console exactly matches `http://localhost:5000/auth/google/callback`
- **"Access blocked"**: Your OAuth consent screen may still be in "Testing" mode. Add your test email under **OAuth consent screen** → **Test users**
- **"This app isn't verified"**: Click **Advanced** → **Go to EcoTracker (unsafe)** during development. This is normal for unverified apps.

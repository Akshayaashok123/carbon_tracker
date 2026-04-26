# Gmail API Setup for Zomato/Swiggy Auto-Logging

## How to Set Up Gmail Integration

Your EcoTracker app can now automatically log Zomato and Swiggy food orders directly from your email! Here's how to enable it:

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Create Project** and name it "EcoTracker"
3. Wait for the project to be created

### Step 2: Enable Gmail API

1. In the Google Cloud Console, search for **"Gmail API"**
2. Click it and select **Enable**

### Step 3: Create OAuth 2.0 Credentials

1. Go to **Credentials** (left sidebar)
2. Click **Create Credentials** → **OAuth client ID**
3. You may be prompted to create an OAuth Consent Screen first:
   - Choose **External** for User Type
   - Fill in the app name: "EcoTracker"
   - Add your email as a test user
   - Go back to Credentials

4. For Application Type, select **Desktop Application**
5. Click **Create**
6. Click the download button (⬇️) on your new credential
7. Save it as `gmail_credentials.json`

### Step 4: Place Credentials File

1. Place the downloaded `gmail_credentials.json` file in your project's `data/` folder:

```
carbon-tracker/
├── app.py
├── static/
├── templates/
├── data/
│   └── gmail_credentials.json  ← Put it here
├── gmail_handler.py
└── ...
```

### Step 5: Install Dependencies

Run:
```bash
pip install -r requirements.txt
```

This installs the Google API client libraries.

### Step 6: Start the App

```bash
python app.py
```

Then go to the onboarding screen and click **"Auto-Log Zomato/Swiggy Orders"** button!

---

## How It Works

1. **Connect Gmail** → You'll be asked to grant EcoTracker read-only access to your emails
2. **Fetch Orders** → The app searches for Zomato/Swiggy order confirmations
3. **Auto-detect Meals** → It parses the email to extract:
   - Restaurant name
   - Meal type (biryani, burger, salad, etc.)
   - Estimated carbon footprint
4. **Log Entry** → One click logs the order with its carbon value to your daily tracker
5. **Earn Points** → +50 points for each Gmail auto-logged order!

---

## What Meals Are Detected?

The app recognizes keywords like:
- **Vegan/Salad**: 0.8-0.9 kg CO₂
- **Vegetarian/Paneer**: 1.5-1.8 kg CO₂
- **Chicken/Fish**: 2.3-2.8 kg CO₂
- **Beef/Lamb/Mutton**: 4.5-5.2 kg CO₂
- **Biryani/Curries**: 2.0-2.2 kg CO₂

If a meal isn't detected correctly, you can still manually enter it!

---

## Privacy & Security

✅ **Read-only access** — EcoTracker only reads your emails, never sends or deletes them  
✅ **Your data stays yours** — Gmail tokens are stored locally in `data/gmail_token.json` only  
✅ **No tracking** — Your meals are only logged in your EcoTracker profile, never shared  

---

## Troubleshooting

- **"Gmail credentials not configured"** → Make sure `data/gmail_credentials.json` exists
- **"redirect_uri_mismatch"** → In Google Cloud Console, create a **Web application** OAuth client and add `http://localhost:5000/api/gmail/callback` as an authorized redirect URI, then replace `data/gmail_credentials.json` with that downloaded JSON.
- **Orders not appearing** → Check that you have received Zomato/Swiggy confirmation emails
- **Token expired** → Click "Auto-Log" button again to refresh
- **"Read-only access" warning** → This is normal! We only need read permission.

---

Enjoy guilt-free food ordering tracking! 🌿

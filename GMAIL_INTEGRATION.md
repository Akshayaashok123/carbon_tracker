# Gmail API Integration - Feature Summary

## ✅ Completed: Auto-Log Zomato/Swiggy Orders

Your EcoTracker can now automatically log food carbon from your Zomato and Swiggy order confirmation emails!

---

## 🎯 What's New

### Backend Changes
- **`gmail_handler.py`** — Gmail OAuth, email parsing, and Zomato/Swiggy detection
- **App routes** — 5 new API endpoints:
  - `/api/gmail/auth` — Initiate OAuth login
  - `/api/gmail/callback` — Handle OAuth callback
  - `/api/gmail/status` — Check connection status
  - `/api/gmail/orders` — Fetch recent orders from emails
  - `/api/gmail/log-order` — Auto-log an order to your profile

### Frontend Changes
- **Gmail button** — "Auto-Log Zomato/Swiggy Orders" on onboarding screen
- **Order modal** — View and click to log recent orders
- **Status indicator** — Shows "✅ Gmail Connected" when authenticated
- **JavaScript functions** — `connectGmail()`, `fetchGmailOrders()`, `showGmailOrders()`, `autoLogGmailOrder()`

### Dependencies Added
```
google-auth-oauthlib
google-auth-httplib2
google-api-python-client
python-dotenv
```

---

## 🚀 User Flow

1. **Connect Gmail**
   - Click "Auto-Log Zomato/Swiggy Orders" on signup
   - Grant read-only Gmail access
   - Credentials saved locally to `data/gmail_token.json`

2. **Fetch Orders**
   - Click button again (now shows "✅ Gmail Connected - View Orders")
   - Modal opens showing recent food orders from emails

3. **Auto-Log**
   - Click any order
   - Carbon value automatically logged
   - +50 points earned
   - Badges checked and awarded

---

## 📧 What It Detects

The parser recognizes:
- **Platform**: Zomato or Swiggy
- **Restaurant**: Extracted from email subject/body
- **Meal type**: 
  - Vegan → 0.8 kg CO₂
  - Vegetarian/Paneer → 1.5-1.8 kg CO₂
  - Chicken → 2.5 kg CO₂
  - Beef/Lamb → 5.2 kg CO₂
  - (+ 20 other keywords)

---

## ⚙️ Configuration Required

Users must:
1. Download OAuth 2.0 credentials from Google Cloud Console
2. Save as `data/gmail_credentials.json`
3. See `GMAIL_SETUP.md` for detailed instructions

---

## 🔒 Security

- ✅ Read-only Gmail access (no send/delete permissions)
- ✅ Tokens stored locally, never sent to external servers
- ✅ No data collection or tracking
- ✅ Transparent OAuth consent screen

---

## 📊 Points System

| Action | Points |
|--------|--------|
| Manual food log | +100 |
| **Gmail auto-log** | **+50** |
| Green day (<5 kg) | +50 |

---

## 🎨 Future Enhancements

Possible additions:
- SMS parsing for Swiggy SMS confirmations
- Automatic daily summary from multiple orders
- Meal recipe carbon breakdown
- Restaurant carbon ratings
- Integration with other food delivery apps (Uber Eats, Zomato premium)

---

## 📝 Files Modified/Created

**Created:**
- `gmail_handler.py` — 370 lines of Gmail integration
- `GMAIL_SETUP.md` — User setup guide
- `data/gmail_credentials_template.json` — Template for credentials

**Modified:**
- `app.py` — Added Gmail imports and 5 new routes (+150 lines)
- `templates/index.html` — Added Gmail button (+1 button)
- `static/main.js` — Added Gmail functions (+180 lines)
- `requirements.txt` — Added 4 new dependencies

---

Enjoy guilt-free sustainability tracking! 🌿📱

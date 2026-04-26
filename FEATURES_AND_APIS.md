# EcoTracker - Features, APIs, and Unique Selling Points (USPs)

This document provides a comprehensive overview of the EcoTracker (Carbon Tracker) application. It details the unique features, the integrations that power them, and all the backend APIs available.

## 1. What Makes the App Unique?

EcoTracker is much more than a standard carbon calculator. It takes a deeply integrated, automated, and gamified approach to tracking structural sustainability day-to-day:

*   **Zero-Friction Logging Ecosystem**: Rather than relying entirely on manual inputs, it plugs right into users' existing workflows. It fetches physical activities via **Strava** integration and extracts carbon costs from food delivery platforms (Zomato/Swiggy) through **Gmail API** scanning.
*   **AI-Powered EcoBot**: Uses a locally-hosted LLM (**Ollama/LLaMa 3.2**) as a digital sustainability coach, generating tailored, context-aware motivation based strictly on the user's daily data input rather than generic tips.
*   **Intelligent Eco-Planner (OLA Maps)**: For any commute, it simultaneously evaluates four different routing contexts to present the *Fastest, Cheapest, and Greenest* route options, assigning a live CO₂ cost for the trip.
*   **Receipt OCR Capability**: Allows users to upload a photo of a physical receipt or bill; using Python Tesseract (OCR), it detects meal types (e.g., Vegetarian, Beef) to estimate the carbon impact of a meal.
*   **Deep Gamification & Social Battles**: Features an intricate badge and streak system (e.g., "Solar Sentinel", "Master Composter"), a persistent competitive Leaderboard, "Department Battles" to foster localized competition, and an economy where points can be redeemed for high-tier actions (e.g., "Tree Planter").
*   **Relatable Equivalents**: Bridges the abstraction gap of emissions by showing what '1 kg of CO₂' means in tangible terms (e.g., 'Hours of Netflix on a Big TV', 'LED Bulbs Left On', or 'Burgers').

---

## 2. Integrated Services & Technologies

*   **Flask (Python)**: Core backend server and API framework.
*   **OLA Maps SDK/API**: Provides Geo-coding, Place Autocomplete, and Route Direction data explicitly mapped against vehicle carbon coefficients.
*   **Ollama (llama3.2:1b)**: Runs in the background to provide the generative AI Carbon Coach.
*   **Pytesseract & OpenCV**: Parses textual content out of image receipts for food carbon calculations.
*   **Google Auth (OAuth 2.0) & Gmail APIs**: Secured flow to pull recent emails, parse Swiggy/Zomato invoices, and automatically estimate meal carbon.
*   **Strava API**: Syncs cycling, walking, and running activities automatically.

---

## 3. Comprehensive Backend APIs

### Core Carbon Calculation
*   `POST /api/calculate`
    *   *Purpose*: Calculates carbon footprint across transport (via OLA Maps dist/routing), food, and electricity. Evaluates route choices to return the fastest/cheapest/greenest options and formats carbon equivalents.

### Generative AI Coach
*   `POST /api/coach`
    *   *Purpose*: Passes daily stats into Ollama; returns a short, personalized motivation/coaching message. 

### Location & Routing (OLA Proxy)
*   `GET /api/autocomplete`
    *   *Purpose*: Proxies requests to OLA Maps to securely search place names without exposing the map API key to the frontend.

### Optical Character Recognition (OCR)
*   `POST /api/ocr-receipt`
    *   *Purpose*: Receives an image file (.png, .jpg), runs text extraction, and identifies meal keywords to assign a carbon value.

### Data Persistence & Gamification
*   `POST /api/save-entry`
    *   *Purpose*: Saves a daily log. Recalculates statistics, streaks, and dynamically awards new badges.
*   `GET /api/badges/<username>`
    *   *Purpose*: Fetches earned badges and streak counts for a single user.
*   `POST /api/award-badge`
    *   *Purpose*: Explicit route to inject a specific badge onto a user profile (e.g., winning a mini-game).
*   `POST /api/redeem-tree`
    *   *Purpose*: Subtracts 5,000 points from the user's score to award the "Tree Planter" badge.

### Leaderboards & Social Data
*   `GET /api/leaderboard`
    *   *Purpose*: Fetches top 10 users ranked by lowest average carbon output. 
*   `GET /api/ranking`
    *   *Purpose*: A specifically formatted leaderboard endpoint with UI icons/colors baked in for the React/Javascript frontend.
*   `GET /api/dept-battle`
    *   *Purpose*: Aggregates data by user departments to pit whole departments against each other in carbon limits.
*   `GET /api/profile/<username>`
    *   *Purpose*: Fetches detailed log history for a single user to build trend visualizers.
*   `GET /api/admin`
    *   *Purpose*: Aggregate metadata fetching total logs, campus wide averages, and total green days.

### Chennai EcoHub & Community
*   `GET /api/eco-events`
    *   *Purpose*: Fetches curated city-wide eco events (cleanups, workshops, tree plantations). Supports category filtering.
*   `GET /api/eco-news`
    *   *Purpose*: Returns recent environmental news articles specific to Chennai and India.
*   `POST /api/eco-events/interest`
    *   *Purpose*: Toggles a user's interest in a specific event, persisting it to `event_interests.json` and updating the global count.
*   `GET /api/eco-events/my-interests/<username>`
    *   *Purpose*: Returns a list of event IDs that the specific user has expressed interest in.

### Strava Integrations
*   `GET /api/strava/auth`: Generates the Strava OAuth login URL.
*   `GET /api/strava/callback`: Completes OAuth flow and passes access tokens down to frontend via window events.
*   `GET /api/strava/activities`: Queries the user's Strava account to find the latest Run/Ride/Walk distance in km.

### Gmail Integrations (Auto-food Logging)
*   `GET /api/gmail/auth`: Initializes Google OAuth 2 flow for read-only Gmail access.
*   `GET /api/gmail/callback`: Intercepts token, stores it locally (`data/gmail_token.json`), and alerts frontend.
*   `GET /api/gmail/status`: Validates if a non-expired Gmail token presently exists in the system.
*   `GET /api/gmail/disconnect`: Deletes stored credentials.
*   `GET /api/gmail/orders`: Scans recent emails to extract structured representations of food delivery receipts.
*   `POST /api/gmail/log-order`: Directly pushes an extracted Gmail order into the user's carbon daily log structure and awards points.

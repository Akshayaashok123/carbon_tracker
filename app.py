from flask import Flask, render_template, request, jsonify, session, redirect
from flask_cors import CORS
from dotenv import load_dotenv
import secrets
import json
import os
import requests
import xml.etree.ElementTree as ET
import threading
import logging
try:
    import pytesseract
    from PIL import Image
    import sys
    
    # Configure Tesseract path for Windows, leave default for Linux
    if sys.platform == 'win32':
        pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    
    OCR_AVAILABLE = True
except Exception as e:
    logger.warning(f"OCR not available: {e}")
    OCR_AVAILABLE = False
import io
from datetime import datetime, date as dt_date, timedelta
import concurrent.futures
from werkzeug.middleware.proxy_fix import ProxyFix
from gmail_handler import fetch_recent_orders
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

load_dotenv()

# ── Production Logging ──────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
CORS(app)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

# ── Optional Rate Limiting (install flask-limiter) ──────────
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter = Limiter(get_remote_address, app=app,
                      default_limits=["120 per minute"],
                      storage_uri="memory://")
    logger.info("Rate limiting enabled")
except ImportError:
    limiter = None
    logger.warning("flask-limiter not installed — rate limiting disabled.")

GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
# Render puts secret files in the root directory, local dev uses data/
GMAIL_CREDENTIALS_FILE = 'gmail_credentials.json' if os.path.exists('gmail_credentials.json') else 'data/gmail_credentials.json'
GMAIL_TOKEN_FILE = 'data/gmail_token.json'

# --- Configuration (loaded from .env) ---
OLA_MAPS_KEY     = os.environ.get("OLA_MAPS_KEY", "")
OLLAMA_URL       = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL     = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")
LEADERBOARD_FILE = "data/leaderboard.json"
GREEN_DAY_LIMIT  = 5.0

# --- Strava Integration (loaded from .env) ---
# Get yours at https://www.strava.com/settings/api
STRAVA_CLIENT_ID     = os.environ.get('STRAVA_CLIENT_ID', '')
STRAVA_CLIENT_SECRET = os.environ.get('STRAVA_CLIENT_SECRET', '')
STRAVA_REDIRECT_URI  = os.environ.get('STRAVA_REDIRECT_URI', 'http://localhost:5000/api/strava/callback')

@app.route('/api/coach', methods=['POST'])
def carbon_coach():
    try:
        data        = request.json
        username    = data.get('username', 'Student')
        transport   = data.get('transport_label', 'Car')
        dist_km     = data.get('distance_km', 0)
        commute_co2 = data.get('breakdown', {}).get('commute', 0)
        food_co2    = data.get('breakdown', {}).get('food', 0)
        elec_co2    = data.get('breakdown', {}).get('electricity', 0)
        total_co2   = data.get('total', 0)
        eco         = data.get('eco_planner', {})
        greenest    = (eco.get('greenest') or {})
        cheapest    = (eco.get('cheapest') or {})

        greenest_line = f"{greenest.get('dist','N/A')} km, {greenest.get('co2',0)} kg CO₂, {greenest.get('time','N/A')} mins" if greenest else "Not available"
        cheapest_line = f"{cheapest.get('dist','N/A')} km, {cheapest.get('co2',0)} kg CO₂, {cheapest.get('time','N/A')} mins" if cheapest else "Not available"

        prompt = f"""You are EcoBot, a friendly campus sustainability coach.
A student named {username} just logged their daily carbon footprint:
- Transport: {transport} over {dist_km} km → {commute_co2} kg CO₂
- Food: {food_co2} kg CO₂
- Electricity: {elec_co2} kg CO₂
- Total: {total_co2} kg CO₂
Greener alternative: {greenest_line}
Cheaper alternative: {cheapest_line}

Write a SHORT (3-4 sentences), warm, specific coaching message for {username}.
Mention their actual numbers. Highlight the single biggest saving they could make.
End with one actionable suggestion. Use 1-2 emojis. Write in natural prose, no bullet points."""

        res = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL, "prompt": prompt,
            "stream": False, "options": {"temperature": 0.7, "num_predict": 200}
        }, timeout=60)
        res.raise_for_status()
        message = res.json().get("response", "").strip()
        if not message:
            return jsonify({"error": "Empty response from Ollama"}), 500
        return jsonify({"message": message})

    except requests.exceptions.Timeout:
        return jsonify({"message": "🌿 EcoBot is loading — this takes ~30s first time. Try again!"}), 200
    except requests.exceptions.ConnectionError:
        return jsonify({"message": "⚠️ Ollama is not running. Open a terminal and run: ollama serve"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# Transport mode config
TRANSPORT_MODES = {
    'car_solo':   ('driving', 0.171, '🚗 Car (Solo)'),
    'carpool':    ('driving', 0.068, '🚗 Carpool (2–3 people)'),
    'motorcycle': ('driving', 0.103, '🏍️ Motorcycle'),
    'bus':        ('driving', 0.089, '🚌 Bus'),
    'metro':      ('driving', 0.041, '🚇 Metro / Train'),
    'bicycle':    ('cycling', 0.0,   '🚲 Bicycle'),
    'walk':       ('walking', 0.0,   '🚶 Walk'),
}

MEAL_IMPACT = {
    "VEGETARIAN": 1.5, "CHICKEN": 2.5,
    "BEEF": 5.2, "LAMB": 5.2, "VEGAN": 0.8
}

# ── Badge definitions ──────────────────────────────────────
# Each badge: id, emoji, name, description
BADGE_DEFS = {
    'green_day':      ('🌱', 'Green Day',        'First day under 5 kg CO₂'),
    'streak_3':       ('🔥', '3-Day Streak',     '3 consecutive green days'),
    'streak_7':       ('⚡', '7-Day Streak',     '7 consecutive green days'),
    'streak_14':      ('🌟', '14-Day Streak',    '14 consecutive green days'),
    'first_cyclist':  ('🚲', 'First Cyclist',    'Commuted by bicycle'),
    'frequent_rider': ('🚴', 'Frequent Rider',   'Cycled 5 times total'),
    'first_walker':   ('🚶', 'First Walker',     'Walked to campus'),
    'transit_lover':  ('🚇', 'Transit Lover',    'Used metro or bus 5 times'),
    'vegan_day':      ('🥗', 'Vegan Day',        'Chose a vegan meal'),
    'vegan_week':     ('🌿', 'Vegan Week',       '7 vegan meals total'),
    'low_energy':     ('💡', 'Energy Saver',     'Electricity under 1 kg CO₂'),
    'carbon_under2':  ('🏅', 'Ultra Green',      'Total under 2 kg CO₂ in a day'),
    'century':        ('💯', 'Century',          'Logged 100 days total'),
    'eco_warrior':    ('🌍', 'Eco Warrior',      'Logged 30 days total'),
    'carbon_positive':('🏆', 'Carbon Positive',  'Beat your real CO₂ in Carbon Catcher game!'),
    'solar_sentinel': ('☀️', 'Solar Sentinel',   'Participate in renewable campus energy projects.'),
    'master_composter':('🔥', 'Master Composter', 'Track organic waste for 30 consecutive days.'),
    'h2o_guardian':   ('💧', 'H2O Guardian',     'Reduce water usage by 20%.'),
    'tree_planter':   ('🌳', 'Tree Planter',     'Redeem 5,000 points for reforestation action.'),
}

def compute_badges_and_streak(user_data):
    """
    Given a user's stored data dict, recompute their badges and current streak.
    Returns (badges: list[str], streak: int, new_badges: list[str])
    """
    logs      = [l for l in user_data.get('daily_logs', []) if 'date' in l]
    if not logs:
        return [], 0, []
    
    old_badges = set(user_data.get('badges', []))
    earned    = set(old_badges)

    # ── Streak: count consecutive green days ending today ──
    today = dt_date.today().isoformat()
    log_dates = sorted({l['date'] for l in logs}, reverse=True)

    streak = 0
    check  = dt_date.today()
    for d_str in log_dates:
        d = dt_date.fromisoformat(d_str)
        if d == check:
            day_logs   = [l for l in logs if l['date'] == d_str]
            day_total  = min(l['total'] for l in day_logs)
            if day_total <= GREEN_DAY_LIMIT:
                streak += 1
                check  = check - timedelta(days=1)
            else: break
        elif d < check: break

    # ── Compost Streak ──
    compost_streak = 0
    check = dt_date.today()
    for d_str in log_dates:
        d = dt_date.fromisoformat(d_str)
        if d == check:
            day_logs = [l for l in logs if l['date'] == d_str]
            if any(l.get('compost') == True for l in day_logs):
                compost_streak += 1
                check = check - timedelta(days=1)
            else: break
        elif d < check: break

    # ── Badge checks ──
    totals     = [l['total']     for l in logs]
    transports = [l['transport'] for l in logs]
    foods      = [l.get('food_value', 1.5) for l in logs]
    water_logs = [l.get('water_usage') for l in logs if l.get('water_usage') is not None]

    if any(t <= GREEN_DAY_LIMIT for t in totals):  earned.add('green_day')
    if streak >= 3:   earned.add('streak_3')
    if streak >= 7:   earned.add('streak_7')
    if streak >= 14:  earned.add('streak_14')
    if 'bicycle' in transports:                    earned.add('first_cyclist')
    if transports.count('bicycle') >= 5:           earned.add('frequent_rider')
    if 'walk' in transports:                       earned.add('first_walker')
    if transports.count('metro') + transports.count('bus') >= 5:
                                                   earned.add('transit_lover')
    if any(f <= 0.8 for f in foods):               earned.add('vegan_day')
    if sum(1 for f in foods if f <= 0.8) >= 7:     earned.add('vegan_week')
    if any(l.get('elec_co2', 99) < 1.0 for l in logs):
                                                   earned.add('low_energy')
    if any(t < 2.0 for t in totals):               earned.add('carbon_under2')
    if len(logs) >= 30:                            earned.add('eco_warrior')
    if len(logs) >= 100:                           earned.add('century')

    # New specialized badges
    if any(l.get('solar') == True for l in logs):  earned.add('solar_sentinel')
    if compost_streak >= 30:                       earned.add('master_composter')
    
    # H2O Guardian: Compare current usage to early baseline
    if len(water_logs) >= 4:
        baseline = sum(water_logs[:3]) / 3
        current  = water_logs[-1]
        if baseline > 0 and (current <= baseline * 0.8):
            earned.add('h2o_guardian')

    new_badges = list(earned - old_badges)
    return list(earned), streak, new_badges

# --- Utility Functions ---
def init_storage():
    if not os.path.exists('data'):
        os.makedirs('data')
    if not os.path.exists(LEADERBOARD_FILE):
        with open(LEADERBOARD_FILE, "w") as f:
            json.dump({}, f)

LEADERBOARD_CACHE = None
LEADERBOARD_LAST_LOAD = 0
_leaderboard_lock = threading.Lock()

def load_leaderboard():
    init_storage()
    with _leaderboard_lock:
        with open(LEADERBOARD_FILE, "r") as f:
            return json.load(f)

def save_leaderboard(data):
    global LEADERBOARD_CACHE, LEADERBOARD_LAST_LOAD
    with _leaderboard_lock:
        with open(LEADERBOARD_FILE, "w") as f:
            json.dump(data, f, indent=4)
        LEADERBOARD_CACHE = data
        LEADERBOARD_LAST_LOAD = datetime.now().timestamp()

def geocode(address):
    """Geocode an address using OLA Maps."""
    url = "https://api.olamaps.io/places/v1/geocode"
    params = {"address": address, "api_key": OLA_MAPS_KEY}
    try:
        r = requests.get(url, params=params, timeout=5).json()
        results = r.get("geocodingResults", [])
        if not results: return None, None
        loc = results[0]["geometry"]["location"]
        return loc["lat"], loc["lng"]
    except Exception as e:
        logger.warning("Geocode failed for address: %s", e)
        return None, None

def get_route_data(origin_lat, origin_lon, dest_lat, dest_lon, mode, co2_factor):
    """Fetch distance and time from OLA Maps Directions API."""
    url = "https://api.olamaps.io/routing/v1/directions"
    params = {
        "origin":      f"{origin_lat},{origin_lon}",
        "destination": f"{dest_lat},{dest_lon}",
        "mode":        mode,
        "api_key":     OLA_MAPS_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=5).json()
        routes = r.get("routes", [])
        if not routes: return None
        leg  = routes[0]["legs"][0]
        dist = leg["distance"]["value"] / 1000   # metres → km
        time = leg["duration"]["value"] / 60     # seconds → minutes
        return {
            "dist": round(dist, 2),
            "time": round(time),
            "co2":  round(dist * co2_factor, 2),
        }
    except Exception as e:
        logger.warning("Route data fetch failed: %s", e)
        return None

# --- Routes ---

@app.after_request
def add_header(response):
    path = request.path
    # Only aggressively cache true static assets (CSS, JS, images)
    if path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    else:
        # HTML pages and API responses must never be stale
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    return response

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/autocomplete')
def autocomplete():
    """Proxy OLA Maps autocomplete — keeps API key off the frontend."""
    q = request.args.get('q', '').strip()
    if len(q) < 3:
        return jsonify([])
    try:
        url = "https://api.olamaps.io/places/v1/autocomplete"
        params = {
            "input":    q,
            "api_key":  OLA_MAPS_KEY,
            "language": "en",
        }
        r = requests.get(url, params=params).json()
        predictions = r.get("predictions", [])
        results = []
        for p in predictions:
            loc = p.get("geometry", {}).get("location", {})
            lat = loc.get("lat")
            lng = loc.get("lng")
            if lat is None or lng is None:
                continue
            sf = p.get("structured_formatting", {})
            results.append({
                "label": p.get("description", ""),
                "main":  sf.get("main_text", p.get("description", "")),
                "sub":   sf.get("secondary_text", ""),
                "lat":   lat,
                "lon":   lng,
                "type":  (p.get("types") or [""])[0],
            })
        return jsonify(results)
    except Exception as e:
        return jsonify([]), 500

@app.route('/api/calculate', methods=['POST'])
def calculate_carbon():
    try:
        data = request.json
        food_impact = float(data.get('food', 0))
        elec_hours = float(data.get('electricity', 0))
        transport_key = data.get('transport', 'car_solo')
        manual_dist   = data.get('distance_km')
        smart_food_calories = float(data.get('smart_food_calories', 0))

        # 1. Calculate Selected Route
        geo_mode, co2_per_km, mode_label = TRANSPORT_MODES.get(
            transport_key, TRANSPORT_MODES['car_solo']
        )

        if manual_dist is not None:
            dist_km     = float(manual_dist)
            commute_co2 = round(dist_km * co2_per_km, 2)
            fastest = cheapest = greenest = None # We don't have route comparisons for manual dist
        else:
            # Coordinates from frontend autocomplete
            o_lat, o_lon = data.get('origin_lat'), data.get('origin_lon')
            d_lat, d_lon = data.get('dest_lat'), data.get('dest_lon')

            # Fallback to geocoding if coords missing
            if not all([o_lat, o_lon, d_lat, d_lon]):
                o_lat, o_lon = geocode(data.get('origin', ''))
                d_lat, d_lon = geocode(data.get('destination', ''))

            if None in (o_lat, o_lon, d_lat, d_lon):
                return jsonify({'error': 'Location not found'}), 400

            # 1. & 2. ECO-PLANNER: Fetch all 4 route options concurrently to save time
            with concurrent.futures.ThreadPoolExecutor() as executor:
                sel_f   = executor.submit(get_route_data, o_lat, o_lon, d_lat, d_lon, geo_mode, co2_per_km)
                fast_f  = executor.submit(get_route_data, o_lat, o_lon, d_lat, d_lon, 'driving', 0.171)
                cheap_f = executor.submit(get_route_data, o_lat, o_lon, d_lat, d_lon, 'driving', 0.041)
                green_f = executor.submit(get_route_data, o_lat, o_lon, d_lat, d_lon, 'cycling', 0.0)
                
                selected_route = sel_f.result()
                fastest        = fast_f.result()
                cheapest       = cheap_f.result()
                greenest       = green_f.result() if (selected_route and selected_route['dist'] <= 15) else cheapest

            dist_km    = selected_route['dist'] if selected_route else 0
            commute_co2 = selected_route['co2'] if selected_route else 0

        elec_co2 = elec_hours * 0.3
        smart_food_impact = float(data.get('smart_food_co2', 0))
        total = commute_co2 + food_impact + elec_co2 + smart_food_impact

        # ── Carbon Equivalents Gallery data ──────────────────────────────
        equivalents = [
            {'emoji':'🍔', 'label':'Beef burgers',      'value': round(total / 6.0,  1), 'unit':'burgers'},
            {'emoji':'🚿', 'label':'Showers',           'value': round(total / 0.5,  1), 'unit':'mins'},
            {'emoji':'📺', 'label':'Netflix on big TV', 'value': round(total / 0.097,1), 'unit':'hours'},
            {'emoji':'✈️', 'label':'Flight time',       'value': round(total / 3.37, 2), 'unit':'hours'},
            {'emoji':'💡', 'label':'LED bulb on',       'value': round(total / 0.008,0), 'unit':'hours'},
            {'emoji':'🌊', 'label':'Arctic ice melted', 'value': round(total * 3.0,  1), 'unit':'m²'},
        ]

        return jsonify({
            'total': round(total, 2),
            'distance_km': round(dist_km, 2),
            'transport_label': mode_label,
            'breakdown': {
                'commute': round(commute_co2, 2),
                'food': round(food_impact, 2),
                'electricity': round(elec_co2, 2)
            },
            'eco_planner': {
                'fastest': fastest,
                'cheapest': cheapest,
                'greenest': greenest
            },
            'calories': round(smart_food_calories),
            'comparisons': {
                'driving_km':    round(total * 5, 1),
                'trees_needed':  max(1, round(total / 21)),
                'phone_charges': round(total * 83333, 0)
            },
            'equivalents': equivalents
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analyze-food-smart', methods=['POST'])
def analyze_food_smart():
    """
    Analyzes food items from either OCR text (receipt) or a direct list.
    Returns estimated calories and carbon footprint.
    """
    text = ""
    source = "list"
    
    if 'file' in request.files:
        if not OCR_AVAILABLE:
            return jsonify({'error': 'OCR not available on server'}), 503
        file = request.files['file']
        img  = Image.open(file.stream)
        text = pytesseract.image_to_string(img)
        source = "receipt"
    else:
        data = request.json
        text = data.get('text', '')
        source = "list"

    if not text.strip():
        return jsonify({'error': 'No text or image provided'}), 400

    prompt = f"""You are a nutrition and sustainability expert.
Analyze this {source} text and extract individual food/drink items.
For each item:
1. Estimate Calories (kcal).
2. Estimate Carbon Footprint (kg CO2e).
3. Return a clean JSON array of objects with keys: "name", "calories", "co2".

Text:
\"\"\"
{text}
\"\"\"

Guidelines:
- If a quantity is mentioned (e.g. "2 Burgers"), calculate for that quantity.
- If it's a receipt, ignore prices/dates, focus only on food items.
- Be realistic with estimates.
- ONLY return the JSON array. No preamble. No markdown blocks."""

    try:
        res = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL, "prompt": prompt,
            "stream": False, "options": {"temperature": 0.2, "num_predict": 500}
        }, timeout=30)
        
        # Clean response if LLM added markdown
        raw_response = res.json().get("response", "").strip()
        if "```json" in raw_response:
            raw_response = raw_response.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_response:
            raw_response = raw_response.split("```")[1].split("```")[0].strip()
            
        items = json.loads(raw_response)
        
        total_calories = sum(i.get('calories', 0) for i in items)
        total_co2 = sum(i.get('co2', 0) for i in items)
        
        return jsonify({
            'items': items,
            'total_calories': round(total_calories),
            'total_co2': round(total_co2, 2),
            'text_extracted': text[:200] + "..." if len(text) > 200 else text
        })

    except Exception as e:
        # Fallback if Ollama fails or returns bad JSON
        return jsonify({
            'error': 'Smart analysis failed. Using basic estimation.',
            'items': [{'name': 'Extracted Items', 'calories': 0, 'co2': 1.5}],
            'total_calories': 0,
            'total_co2': 1.5
        })

@app.route('/api/ocr-receipt', methods=['POST'])
def ocr_receipt():
    # Keep this for backward compatibility or remove if unused
    return analyze_food_smart()

@app.route('/api/save-entry', methods=['POST'])
def save_entry():
    try:
        data        = request.json
        raw_user    = data.get('username', 'Anonymous').strip() or 'Anonymous'
        username    = ''.join(c for c in raw_user if c.isalnum() or c in ' ._-')[:50] or 'Anonymous'
        department  = data.get('department', 'General').strip()[:50] or 'General'
        total       = max(0, min(float(data.get('total', 0)), 500))
        transport   = data.get('transport', 'car_solo')
        if transport not in TRANSPORT_MODES:
            transport = 'car_solo'
        food_value  = max(0, min(float(data.get('food_value', 1.5)), 100))
        elec_co2    = max(0, min(float(data.get('elec_co2', 0)), 100))
        calories    = max(0, min(int(data.get('calories', 0)), 50000))
        today       = dt_date.today().isoformat()

        board = load_leaderboard()
        if username not in board:
            board[username] = {
                'entries': [], 'avg_carbon': 0,
                'department': department,
                'daily_logs': [], 'badges': [], 'streak': 0,
                'points': 0
            }

        u = board[username]
        u['department'] = department
        u['entries'].append(total)
        u['avg_carbon'] = round(sum(u['entries']) / len(u['entries']), 2)

        # Award points: 100 per log, +50 if green day
        u.setdefault('points', 0)
        u['points'] += 100
        if total <= GREEN_DAY_LIMIT:
            u['points'] += 50

        # Append today's detailed log
        u.setdefault('daily_logs', []).append({
            'date':      today,
            'total':     total,
            'transport': transport,
            'food_value': food_value,
            'elec_co2':  elec_co2,
            'compost':   data.get('compost', False),
            'solar':     data.get('solar', False),
            'water_usage': data.get('water_usage'),
            'calories': calories
        })
        
        # Track total calories for the user
        u['total_calories'] = u.get('total_calories', 0) + calories

        # Recompute badges and streak
        all_badges, streak, new_badges = compute_badges_and_streak(u)
        u['badges'] = all_badges
        u['streak'] = streak

        save_leaderboard(board)

        # Return badge details so frontend can celebrate
        new_badge_details = [
            {'id': bid, 'emoji': BADGE_DEFS[bid][0],
             'name': BADGE_DEFS[bid][1], 'desc': BADGE_DEFS[bid][2]}
            for bid in new_badges if bid in BADGE_DEFS
        ]
        all_badge_details = [
            {'id': bid, 'emoji': BADGE_DEFS[bid][0],
             'name': BADGE_DEFS[bid][1], 'desc': BADGE_DEFS[bid][2]}
            for bid in all_badges if bid in BADGE_DEFS
        ]

        return jsonify({
            'success':    True,
            'streak':     streak,
            'points':     u.get('points', 0),
            'new_badges': new_badge_details,
            'all_badges': all_badge_details
        })
    except Exception as e:
        logger.exception("save-entry failed")
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


@app.route('/api/badges/<username>', methods=['GET'])
def get_badges(username):
    """Return current streak + all badges for a user."""
    try:
        board = load_leaderboard()
        if username not in board:
            return jsonify({'streak': 0, 'points': 0, 'badges': []})
        u = board[username]
        badges = [
            {'id': bid, 'emoji': BADGE_DEFS[bid][0],
             'name': BADGE_DEFS[bid][1], 'desc': BADGE_DEFS[bid][2]}
            for bid in u.get('badges', []) if bid in BADGE_DEFS
        ]
        return jsonify({
            'streak': u.get('streak', 0),
            'points': u.get('points', 0),
            'badges': badges,
            'calories': u.get('total_calories', 0),
            'avg_carbon': u.get('avg_carbon', 0),
        })
    except Exception as e:
        return jsonify({'streak': 0, 'badges': [], 'error': str(e)})

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    board = load_leaderboard()
    dept_filter = request.args.get('dept', '').strip()

    all_users = [
        {
            'username':   k,
            'avg_carbon': v.get('avg_carbon', 0),
            'department': v.get('department', '—'),
            'entries':    len(v.get('entries', [])),
            'streak':     v.get('streak', 0),
            'points':     v.get('points', 0),
            'badges':     [BADGE_DEFS[b][0] for b in v.get('badges', []) if b in BADGE_DEFS]
        }
        for k, v in board.items()
    ]

    if dept_filter:
        all_users = [u for u in all_users if u['department'] == dept_filter]

    ranked = sorted(all_users, key=lambda x: x['avg_carbon'])
    return jsonify(ranked[:15])

@app.route('/api/award-badge', methods=['POST'])
def award_badge():
    """Award a specific badge to a user (e.g. from game)."""
    try:
        data     = request.json
        username = data.get('username', '').strip()
        badge_id = data.get('badge', '')
        if not username or badge_id not in BADGE_DEFS:
            return jsonify({'success': False}), 400
        board = load_leaderboard()
        if username not in board:
            return jsonify({'success': False}), 404
        badges = board[username].get('badges', [])
        if badge_id not in badges:
            badges.append(badge_id)
            board[username]['badges'] = badges
            save_leaderboard(board)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/redeem-tree', methods=['POST'])
def redeem_tree():
    """Spend 5,000 points for a Tree Planter badge."""
    try:
        data     = request.json
        username = data.get('username', '').strip()
        if not username: return jsonify({'success': False, 'error': 'No user'}), 400
        
        board = load_leaderboard()
        if username not in board: return jsonify({'success': False, 'error': 'Not found'}), 404
        
        u = board[username]
        pts = u.get('points', 0)
        if pts < 5000:
            return jsonify({'success': False, 'error': 'Not enough points (need 5,000)'}), 400
            
        u['points'] = pts - 5000
        badges = set(u.get('badges', []))
        if 'tree_planter' not in badges:
            badges.add('tree_planter')
            u['badges'] = list(badges)
            save_leaderboard(board)
            return jsonify({'success': True, 'points': u['points'], 'new_badge': True})
        
        save_leaderboard(board)
        return jsonify({'success': True, 'points': u['points'], 'new_badge': False})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/dept-battle', methods=['GET'])
def dept_battle():
    """Aggregate avg CO₂ and member count by department."""
    try:
        board = load_leaderboard()
        dept_map = {}
        for user, data in board.items():
            dept = data.get('department', 'Other')
            if dept not in dept_map:
                dept_map[dept] = {'total_co2': 0, 'members': 0, 'logs': 0,
                                  'top_streak': 0, 'badges_count': 0}
            d = dept_map[dept]
            d['members']      += 1
            d['logs']         += len(data.get('entries', []))
            d['total_co2']    += data.get('avg_carbon', 0)
            d['top_streak']    = max(d['top_streak'], data.get('streak', 0))
            d['badges_count'] += len(data.get('badges', []))

        result = []
        for dept, d in dept_map.items():
            avg = round(d['total_co2'] / d['members'], 2) if d['members'] else 0
            result.append({
                'department':   dept,
                'avg_co2':      avg,
                'members':      d['members'],
                'total_logs':   d['logs'],
                'top_streak':   d['top_streak'],
                'badges_count': d['badges_count'],
            })
        result.sort(key=lambda x: x['avg_co2'])
        return jsonify(result)
    except Exception as e:
        return jsonify([])

# --- ACTIVITY / STRAVA LIVE DATA ---

@app.route('/api/strava/oauth', methods=['GET'])
def strava_oauth():
    """Redirects the user to the Strava authorization page."""
    # We request the 'activity:read_all' scope to pull polylines
    url = (f"https://www.strava.com/oauth/authorize?client_id={STRAVA_CLIENT_ID}"
           f"&response_type=code&redirect_uri={STRAVA_REDIRECT_URI}&approval_prompt=force&scope=activity:read_all")
    return redirect(url)

@app.route('/api/strava/callback', methods=['GET'])
def strava_callback():
    """Handles the OAuth callback, exchanges code for tokens, saves to leaderboard."""
    code = request.args.get('code')
    error = request.args.get('error')
    
    if error or not code:
        return "Authorization failed or denied. You can close this window and try again."

    # Exchange code for access token
    token_url = "https://www.strava.com/oauth/token"
    payload = {
        'client_id': STRAVA_CLIENT_ID,
        'client_secret': STRAVA_CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code'
    }
    
    res = requests.post(token_url, data=payload)
    if res.status_code != 200:
        return f"Failed to exchange token. Error: {res.text}"

    token_data = res.json()
    access_token = token_data.get('access_token')
    refresh_token = token_data.get('refresh_token')
    expires_at = token_data.get('expires_at')
    
    # Store token securely in session so the frontend can trigger sync
    session['strava_access_token'] = access_token
    session['strava_refresh_token'] = refresh_token
    session['strava_expires_at'] = expires_at

    # Redirect back to frontend
    return redirect('/#activity')

@app.route('/api/strava/sync', methods=['POST'])
def sync_strava():
    """Fetches real recent activities from Strava for the user."""
    access_token = session.get('strava_access_token')
    
    if not access_token:
        return jsonify({"success": False, "error": "Not authenticated with Strava. Please connect your account first."}), 401

    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        activities_url = "https://www.strava.com/api/v3/athlete/activities?per_page=15"
        res = requests.get(activities_url, headers=headers)
        
        if res.status_code != 200:
            return jsonify({"success": False, "error": f"Strava API Error: {res.status_code}"}), 500
            
        raw_activities = res.json()
        formatted_activities = []
        
        for act in raw_activities:
            # We only care about human-powered outdoor transit for carbon offsets
            if act.get('type') not in ['Run', 'Ride', 'Walk', 'Hike']:
                continue
                
            dist_km = act.get('distance', 0) / 1000.0
            moving_time_min = act.get('moving_time', 0) // 60
            
            # Approximate calculation: ~0.21 kg CO2 avoided per km 
            carbon_saved = dist_km * 0.21

            formatted_activities.append({
                "id": str(act.get('id')),
                "type": act.get('type'),
                "name": act.get('name', 'Activity'),
                "distance_km": round(dist_km, 2),
                "moving_time_min": moving_time_min,
                "date": act.get('start_date_local'),
                "carbon_saved": round(carbon_saved, 1),
                "polyline": act.get('map', {}).get('summary_polyline', "")
            })

        # Calculate total points
        rewarded_points = int(sum(a['carbon_saved'] * 50 for a in formatted_activities))
        
        # Credit points to user leaderboard if username was passed
        data = request.json
        username = data.get('username', 'Anonymous').strip() if data else 'Anonymous'
        if username != 'Anonymous':
            board = load_leaderboard()
            if username in board:
                board[username]['points'] = board[username].get('points', 0) + rewarded_points
                save_leaderboard(board)

        return jsonify({"success": True, "activities": formatted_activities, "rewarded_points": rewarded_points})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/ranking', methods=['GET'])
def get_ranking():
    """
    Returns leaderboard data shaped for the React Leaderboard component.
    Each entry includes: id, name, badges (emojis), dept, carbon, icon, iconColor.
    """
    RANK_ICONS = [
        (1, "🏆", "text-yellow-500"),
        (2, "🥈", "text-slate-300"),
        (3, "🥉", "text-amber-600"),
    ]

    try:
        board = load_leaderboard()
        sorted_users = sorted(
            [{'username':   k,
              'avg_carbon': v.get('avg_carbon', 0),
              'department': v.get('department', '—'),
              'badges':     [BADGE_DEFS[b][0] for b in v.get('badges', []) if b in BADGE_DEFS],
             } for k, v in board.items()],
            key=lambda x: x['avg_carbon']
        )[:10]

        result = []
        for idx, user in enumerate(sorted_users):
            rank = idx + 1
            if rank <= 3:
                icon, icon_color = RANK_ICONS[rank - 1][1], RANK_ICONS[rank - 1][2]
            else:
                icon, icon_color = "🏅", "text-green-400"

            result.append({
                'id':        rank,
                'name':      user['username'],
                'badges':    user['badges'],
                'dept':      user['department'],
                'carbon':    round(user['avg_carbon'], 2),
                'icon':      icon,
                'iconColor': icon_color,
            })

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/profile/<username>', methods=['GET'])
def get_profile(username):
    """Return user's daily_logs for trend visualization."""
    try:
        board = load_leaderboard()
        if username not in board:
            return jsonify({'daily_logs': []})
        return jsonify({'daily_logs': board[username].get('daily_logs', [])})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin', methods=['GET'])
def get_admin_stats():
    """Return aggregate campus statistics."""
    admin_token = request.args.get('token')
    if admin_token != app.secret_key and admin_token != os.environ.get("ADMIN_TOKEN", "supersecret"):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        board = load_leaderboard()
        total_logs = 0
        total_co2 = 0
        total_users = len(board)
        green_days = 0

        for user, data in board.items():
            total_logs += len(data.get('entries', []))
            total_co2 += sum(data.get('entries', []))
            for log in data.get('daily_logs', []):
                if log.get('total', float('inf')) <= GREEN_DAY_LIMIT:
                    green_days += 1
        
        campus_avg = round(total_co2 / total_logs, 2) if total_logs > 0 else 0
        return jsonify({
            'total_users': total_users,
            'total_logs': total_logs,
            'total_co2': round(total_co2, 2),
            'campus_avg': campus_avg,
            'green_days': green_days
        })
    except Exception as e:
        logger.exception("admin stats failed")
        return jsonify({'error': 'Failed to load admin stats'}), 500

# ── Gmail Routes for Zomato/Swiggy Auto-Logging ──────────────────────────

@app.route('/api/gmail/auth')
def gmail_auth():
    """Initiate Gmail OAuth 2.0 flow."""
    try:
        session.pop('gmail_state', None)
        session.pop('gmail_redirect_uri', None)
        session.pop('gmail_code_verifier', None)

        # Check if credentials file exists
        if not os.path.exists(GMAIL_CREDENTIALS_FILE):
            return jsonify({
                "error": "Gmail credentials not configured",
                "message": "Download OAuth 2.0 credentials from Google Cloud and save to data/gmail_credentials.json"
            }), 400
        
        flow = InstalledAppFlow.from_client_secrets_file(
            GMAIL_CREDENTIALS_FILE,
            GMAIL_SCOPES
        )
        
        # Use the same host the user is currently on (localhost vs 127.0.0.1)
        redirect_uri = f"{request.host_url.rstrip('/')}/api/gmail/callback"
        flow.redirect_uri = redirect_uri
        auth_url, state = flow.authorization_url(
            prompt='consent',
            access_type='offline',
            include_granted_scopes='true'
        )
        
        # Store state in session for verification
        session['gmail_state'] = state
        session['gmail_redirect_uri'] = redirect_uri
        # Persist PKCE verifier for callback token exchange
        session['gmail_code_verifier'] = getattr(flow, 'code_verifier', None)
        
        return jsonify({"url": auth_url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/gmail/callback')
def gmail_callback():
    """Handle Gmail OAuth callback."""
    try:
        state = request.args.get('state')
        auth_code = request.args.get('code')

        if not state or state != session.get('gmail_state'):
            return "Error: Invalid OAuth state", 400
        
        if not auth_code:
            return "Error: No authorization code received", 400
        
        # Exchange code for credentials
        flow = InstalledAppFlow.from_client_secrets_file(
            GMAIL_CREDENTIALS_FILE,
            GMAIL_SCOPES
        )
        flow.redirect_uri = session.get('gmail_redirect_uri') or f"{request.host_url.rstrip('/')}/api/gmail/callback"
        code_verifier = session.get('gmail_code_verifier')
        if code_verifier:
            flow.code_verifier = code_verifier
        flow.fetch_token(code=auth_code)
        creds = flow.credentials

        # Clear one-time OAuth state after successful callback
        session.pop('gmail_state', None)
        session.pop('gmail_redirect_uri', None)
        session.pop('gmail_code_verifier', None)
        
        # Save credentials
        with open(GMAIL_TOKEN_FILE, 'w') as f:
            json.dump({
                'token': creds.token,
                'refresh_token': creds.refresh_token,
                'token_uri': getattr(creds, 'token_uri', 'https://oauth2.googleapis.com/token'),
                'client_id': creds.client_id,
                'client_secret': creds.client_secret,
                'scopes': creds.scopes,
            }, f)
        
        # Redirect back to app
        html = """
        <html><body style="font-family: Arial; text-align: center; padding: 50px;">
        <h2>🎉 Gmail Connected Successfully!</h2>
        <p>EcoTracker can now auto-log your Zomato & Swiggy orders.</p>
        <p>You can close this window and refresh the app.</p>
        <script>
            if (window.opener) {
                window.opener.postMessage('gmail_connected', window.location.origin);
                setTimeout(() => window.close(), 2000);
            } else {
                setTimeout(() => window.location.href = "/", 2000);
            }
        </script>
        </body></html>
        """
        return html
    except Exception as e:
        return f"Error during Gmail callback: {str(e)}", 500

@app.route('/api/gmail/status')
def gmail_status():
    """Check if Gmail is connected."""
    try:
        if not os.path.exists(GMAIL_TOKEN_FILE):
            return jsonify({"connected": False})
        
        # Try to load and use credentials
        with open(GMAIL_TOKEN_FILE, 'r') as f:
            creds_data = json.load(f)

        creds = Credentials.from_authorized_user_info(creds_data, GMAIL_SCOPES)
        
        # Refresh if expired
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        
        if creds.valid:
            return jsonify({"connected": True})
        else:
            return jsonify({"connected": False})
    except Exception as e:
        return jsonify({"connected": False, "error": str(e)})

@app.route('/api/gmail/disconnect')
def gmail_disconnect():
    """Disconnect Gmail integration."""
    try:
        if os.path.exists(GMAIL_TOKEN_FILE):
            os.remove(GMAIL_TOKEN_FILE)
        return jsonify({"success": True, "message": "Gmail disconnected"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/gmail/orders')
def get_gmail_orders():
    """Fetch recent Zomato/Swiggy orders from Gmail."""
    try:
        if not os.path.exists(GMAIL_TOKEN_FILE):
            return jsonify({"error": "Gmail not connected"}), 401
        
        # Load and validate credentials
        with open(GMAIL_TOKEN_FILE, 'r') as f:
            creds_data = json.load(f)

        creds = Credentials.from_authorized_user_info(creds_data, GMAIL_SCOPES)
        
        # Refresh if expired
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save refreshed token
            with open(GMAIL_TOKEN_FILE, 'w') as f:
                json.dump({
                    'token': creds.token,
                    'refresh_token': creds.refresh_token,
                    'token_uri': getattr(creds, 'token_uri', 'https://oauth2.googleapis.com/token'),
                    'client_id': creds.client_id,
                    'client_secret': creds.client_secret,
                    'scopes': creds.scopes,
                }, f)
        
        from googleapiclient.discovery import build
        service = build('gmail', 'v1', credentials=creds)
        
        # Fetch recent orders
        orders = fetch_recent_orders(service, max_results=15)
        
        # Format for frontend
        formatted_orders = []
        for order in orders:
            formatted_orders.append({
                'date': order['date'],
                'platform': order['platform'],
                'restaurant': order['restaurant'],
                'items': ', '.join(order['items']) if order['items'] else 'Items not detected',
                'carbon_estimate': round(order['carbon_estimate'], 2),
                'subject': order.get('subject', ''),
            })
        
        return jsonify({"orders": formatted_orders, "count": len(formatted_orders)})
    except Exception as e:
        logger.exception("gmail/orders failed")
        return jsonify({"error": "Failed to fetch orders."}), 500

@app.route('/api/gmail/log-order', methods=['POST'])
def log_gmail_order():
    """Auto-log a food order from Gmail into the daily tracker."""
    try:
        data = request.json
        username = data.get('username', 'Anonymous').strip() or 'Anonymous'
        department = data.get('department', 'General').strip() or 'General'
        
        # Extract order details from Gmail
        carbon_from_email = float(data.get('carbon_estimate', 1.5))
        restaurant = data.get('restaurant', 'Unknown Restaurant')
        platform = data.get('platform', 'Delivery')
        items = data.get('items', '')
        
        # Load existing data
        board = load_leaderboard()
        if username not in board:
            board[username] = {
                'entries': [], 'avg_carbon': 0,
                'department': department,
                'daily_logs': [], 'badges': [], 'streak': 0,
                'points': 0
            }
        
        today = dt_date.today().isoformat()
        u = board[username]
        
        # Add food entry
        u['entries'].append(carbon_from_email)
        u['avg_carbon'] = round(sum(u['entries']) / len(u['entries']), 2)
        u['department'] = department
        
        # Award points: 50 for auto-logging from Gmail
        u.setdefault('points', 0)
        u['points'] += 50  # Lower than manual entry (100) but still rewarding
        
        # Create log entry with restaurant info
        u.setdefault('daily_logs', []).append({
            'date': today,
            'total': carbon_from_email,
            'food_value': carbon_from_email,
            'transport': 'none',
            'elec_co2': 0.0,
            'source': f'{platform} - {restaurant}',
            'items': items,
            'compost': False,
            'solar': False,
            'water_usage': None
        })
        
        # Recompute badges and streak
        all_badges, streak, new_badges = compute_badges_and_streak(u)
        u['badges'] = all_badges
        u['streak'] = streak
        
        save_leaderboard(board)
        
        # Return badge details
        new_badge_details = [
            {'id': bid, 'emoji': BADGE_DEFS[bid][0],
             'name': BADGE_DEFS[bid][1], 'desc': BADGE_DEFS[bid][2]}
            for bid in new_badges if bid in BADGE_DEFS
        ]
        
        return jsonify({
            'success': True,
            'points': u.get('points', 0),
            'streak': streak,
            'message': f"✅ Logged {carbon_from_email}kg CO₂ from {restaurant}",
            'new_badges': new_badge_details
        })
    except Exception as e:
        logger.exception("gmail/log-order failed")
        return jsonify({'success': False, 'error': 'Failed to log order.'}), 500


ECOHUB_FILE = "data/chennai_events.json"

def load_ecohub_data():
    """Load curated Chennai eco events and news from JSON file."""
    try:
        if os.path.exists(ECOHUB_FILE):
            with open(ECOHUB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"events": [], "news": []}


@app.route('/api/eco-events')
def get_eco_events():
    """Return curated Chennai eco events, optionally filtered by category."""
    try:
        data = load_ecohub_data()
        events = data.get("events", [])
        category = request.args.get("category", "").strip().lower()
        if category and category != "all":
            events = [e for e in events if e.get("category", "").lower() == category]

        # Sort by date (upcoming first)
        events.sort(key=lambda e: e.get("date", ""))

        # Add interested count from stored data
        interested = _load_interests()
        for evt in events:
            evt["interested_count"] = len(interested.get(evt["id"], []))

        return jsonify({"events": events, "count": len(events)})
    except Exception as e:
        return jsonify({"events": [], "error": str(e)}), 500


def fetch_live_news(fallback_data):
    try:
        url = "https://news.google.com/rss/search?q=environment+OR+climate+change+Chennai&hl=en-IN&gl=IN&ceid=IN:en"
        res = requests.get(url, timeout=5)
        root = ET.fromstring(res.text)
        
        news_items = []
        for item in root.findall('.//channel/item')[:8]:
            title = item.find('title').text
            link = item.find('link').text
            pubDate = item.find('pubDate').text
            
            source_tag = item.find('source')
            source = source_tag.text if source_tag is not None else "Google News"
            
            # Clean title
            if " - " in title:
                title_parts = title.rsplit(" - ", 1)
                title = title_parts[0]
                if len(title_parts) > 1 and source == "Google News":
                    source = title_parts[1]
                    
            news_items.append({
                "id": link,
                "title": title,
                "source": source,
                "date": pubDate,
                "summary": "Live update from " + source,
                "url": link,
                "category": "news",
                "emoji": "📰"
            })
            
        if news_items:
            return news_items
    except Exception as e:
        print("RSS fetch failed: ", e)
        
    return fallback_data.get("news", [])

@app.route('/api/eco-news')
def get_eco_news():
    """Return live environmental news articles about Chennai/India."""
    try:
        data = load_ecohub_data()
        news = fetch_live_news(data)
        return jsonify({"news": news, "count": len(news)})
    except Exception as e:
        return jsonify({"news": [], "error": str(e)}), 500


INTERESTS_FILE = "data/event_interests.json"

def _load_interests():
    try:
        if os.path.exists(INTERESTS_FILE):
            with open(INTERESTS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_interests(data):
    with open(INTERESTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


@app.route('/api/eco-events/interest', methods=['POST'])
def toggle_interest():
    """Toggle a user's interest in an eco event."""
    try:
        body = request.json
        event_id = body.get("event_id", "")
        username = body.get("username", "").strip()
        if not event_id or not username:
            return jsonify({"success": False, "error": "Missing fields"}), 400

        interests = _load_interests()
        if event_id not in interests:
            interests[event_id] = []

        if username in interests[event_id]:
            interests[event_id].remove(username)
            _save_interests(interests)
            return jsonify({"success": True, "interested": False,
                            "count": len(interests[event_id])})
        else:
            interests[event_id].append(username)
            _save_interests(interests)
            return jsonify({"success": True, "interested": True,
                            "count": len(interests[event_id])})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/eco-events/my-interests/<username>')
def get_my_interests(username):
    """Return list of event IDs a user is interested in."""
    try:
        interests = _load_interests()
        my = [eid for eid, users in interests.items() if username in users]
        return jsonify({"interests": my})
    except Exception as e:
        return jsonify({"interests": [], "error": str(e)}), 500


if __name__ == '__main__':
    init_storage()
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.environ.get("PORT", 5000))
    if debug_mode:
        app.run(debug=True, host='0.0.0.0', port=port)
    else:
        try:
            from waitress import serve
            logger.info("Starting production server (Waitress) on port %s", port)
            serve(app, host='0.0.0.0', port=port)
        except ImportError:
            logger.warning("Waitress not installed — falling back to Flask dev server.")
            app.run(debug=False, host='0.0.0.0', port=port)
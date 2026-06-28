"""
EcoTracker — Campus Carbon Tracking Application
=================================================
Professional-grade Flask backend with:
  - PostgreSQL database (SQLAlchemy ORM)
  - Google OAuth authentication
  - Rate limiting, CSRF protection
  - Production server (Waitress)
"""
from flask import Flask, render_template, request, jsonify, session, redirect
from flask_cors import CORS
from flask_login import login_required, current_user
from dotenv import load_dotenv
import json
import os
import requests
import xml.etree.ElementTree as ET
import logging
import concurrent.futures
from datetime import datetime, date as dt_date, timedelta
from werkzeug.middleware.proxy_fix import ProxyFix

try:
    import pytesseract
    from PIL import Image
    import sys
    if sys.platform == 'win32':
        pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

load_dotenv()

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ── App Factory ───────────────────────────────────────────────
from config import Config
from models import db, User, DailyLog, UserBadge, EventInterest
from auth import init_auth
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

@app.before_request
def ignore_content_type_on_get():
    """Clear stray Content-Type on GET requests to avoid 415 errors."""
    if request.method == 'GET' and request.headers.get('Content-Type'):
        request.environ.pop('CONTENT_TYPE', None)
app.config.from_object(Config)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
CORS(app, supports_credentials=True)

# Initialize database
db.init_app(app)

# Initialize authentication (Google OAuth + Flask-Login)
init_auth(app)

# ── Rate Limiting ─────────────────────────────────────────────
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

# ── Constants ─────────────────────────────────────────────────
GREEN_DAY_LIMIT = Config.GREEN_DAY_LIMIT
OLA_MAPS_KEY = Config.OLA_MAPS_KEY
OLLAMA_URL = Config.OLLAMA_URL
OLLAMA_MODEL = Config.OLLAMA_MODEL
STRAVA_CLIENT_ID = Config.STRAVA_CLIENT_ID
STRAVA_CLIENT_SECRET = Config.STRAVA_CLIENT_SECRET
STRAVA_REDIRECT_URI = Config.STRAVA_REDIRECT_URI
CALORIENINJAS_API_KEY = Config.CALORIENINJAS_API_KEY
ELECTRICITY_MAPS_API_KEY = Config.ELECTRICITY_MAPS_API_KEY

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

# ── Badge Definitions ─────────────────────────────────────────
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
    'transit_king':   ('👑', 'Transit King',     'Logged a streak of 5+ green days and a day under 2 kg CO₂'),
}


# ══════════════════════════════════════════════════════════════
#  BADGE & STREAK COMPUTATION (DB-backed)
# ══════════════════════════════════════════════════════════════

def compute_badges_and_streak(user):
    """
    Recompute badges and streak for a user from their DB records.
    Returns (all_badge_ids, streak, new_badge_ids)
    """
    logs = user.daily_logs.order_by(DailyLog.date).all()
    if not logs:
        return [], 0, []

    old_badges = set(user.badge_ids())
    earned = set(old_badges)

    # ── Streak: consecutive green days ending today ──
    log_dates = sorted({l.date for l in logs}, reverse=True)
    streak = 0
    check = dt_date.today()
    for d in log_dates:
        if d == check:
            day_total = min(l.total for l in logs if l.date == d)
            if day_total <= GREEN_DAY_LIMIT:
                streak += 1
                check = check - timedelta(days=1)
            else:
                break
        elif d < check:
            break

    # ── Compost streak ──
    compost_streak = 0
    check = dt_date.today()
    for d in log_dates:
        if d == check:
            if any(l.compost for l in logs if l.date == d):
                compost_streak += 1
                check = check - timedelta(days=1)
            else:
                break
        elif d < check:
            break

    # ── Badge checks ──
    totals = [l.total for l in logs]
    transports = [l.transport for l in logs]
    foods = [l.food_value for l in logs]
    water_logs = [l.water_usage for l in logs if l.water_usage is not None]

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
    if any(l.elec_co2 < 1.0 for l in logs):        earned.add('low_energy')
    if any(t < 2.0 for t in totals):               earned.add('carbon_under2')
    if len(logs) >= 30:                            earned.add('eco_warrior')
    if len(logs) >= 100:                           earned.add('century')
    if any(l.solar for l in logs):                 earned.add('solar_sentinel')
    if compost_streak >= 30:                       earned.add('master_composter')

    if streak >= 5 and any(t < 2.0 for t in totals):
        earned.add('transit_king')

    if len(water_logs) >= 4:
        baseline = sum(water_logs[:3]) / 3
        current = water_logs[-1]
        if baseline > 0 and (current <= baseline * 0.8):
            earned.add('h2o_guardian')

    new_badges = list(earned - old_badges)

    # Persist new badges to DB
    for badge_id in new_badges:
        if not UserBadge.query.filter_by(user_id=user.id, badge_id=badge_id).first():
            db.session.add(UserBadge(user_id=user.id, badge_id=badge_id))

    return list(earned), streak, new_badges


# ══════════════════════════════════════════════════════════════
#  HELPER: Resolve the acting user (auth or legacy name)
# ══════════════════════════════════════════════════════════════

def get_acting_user(data=None):
    """
    Return the User object for the current request.
    Prefers Flask-Login session; falls back to username in request body.
    """
    if current_user.is_authenticated:
        return current_user

    if data is None:
        # Only attempt to parse JSON when the request content type is application/json
        if request.is_json:
            data = request.get_json()
        else:
            data = {}
    username = (data.get('username') or '').strip()[:100]
    if not username:
        return None
    user = User.query.filter_by(name=username).first()
    return user


# ══════════════════════════════════════════════════════════════
#  GEO / ROUTE HELPERS
# ══════════════════════════════════════════════════════════════

def geocode(address):
    """Geocode an address using OLA Maps."""
    url = "https://api.olamaps.io/places/v1/geocode"
    params = {"address": address, "api_key": OLA_MAPS_KEY}
    try:
        r = requests.get(url, params=params, timeout=5).json()
        results = r.get("geocodingResults", [])
        if not results:
            return None, None
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
        r = requests.post(url, params=params, timeout=5).json()
        routes = r.get("routes", [])
        if not routes:
            return None
        leg = routes[0]["legs"][0]
        
        dist_val = leg.get("distance", 0)
        dist = dist_val.get("value", 0) / 1000 if isinstance(dist_val, dict) else float(dist_val) / 1000
        
        dur_val = leg.get("duration", 0)
        time = dur_val.get("value", 0) / 60 if isinstance(dur_val, dict) else float(dur_val) / 60
        return {
            "dist": round(dist, 2),
            "time": round(time),
            "co2":  round(dist * co2_factor, 2),
        }
    except Exception as e:
        logger.warning("Route data fetch failed: %s", e)
        return None



def _load_events():
    events_path = os.path.join(os.path.dirname(__file__), 'data', 'events.json')
    if not os.path.exists(events_path):
        return []
    with open(events_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def _save_events(events):
    events_path = os.path.join(os.path.dirname(__file__), 'data', 'events.json')
    with open(events_path, 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=2)

@app.route('/api/events', methods=['GET'])
def get_events():
    """Return the list of campus events."""
    try:
        events = _load_events()
        return jsonify({'success': True, 'events': events})
    except Exception as e:
        logger.exception('Failed to load events')
        return jsonify({'success': False, 'error': str(e)}), 500

# Duplicate simple matchmaker endpoint removed – using detailed implementation below

# ══════════════════════════════════════════════════════════════
#  MIDDLEWARE
# ══════════════════════════════════════════════════════════════

@app.after_request
def add_header(response):
    path = request.path
    if path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    else:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    return response


# ══════════════════════════════════════════════════════════════
#  GLOBAL ERROR HANDLERS
# ══════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({"success": False, "error": "Endpoint not found"}), 404
    return render_template('index.html'), 404

@app.errorhandler(500)
def server_error(e):
    logger.exception("Internal server error")
    return jsonify({"success": False, "error": "Internal server error"}), 500


# ══════════════════════════════════════════════════════════════
#  ROUTES
# ══════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/health')
def health_check():
    """Health check endpoint for Render and monitoring."""
    try:
        db.session.execute(db.text("SELECT 1"))
        return jsonify({"status": "healthy", "database": "connected"})
    except Exception as e:
        return jsonify({"status": "unhealthy", "database": str(e)}), 500

@app.route('/api/wallet', methods=['GET', 'POST'])
@login_required

def wallet_api():
    """Handle wallet data.

    GET  – returns the current wallet info (browser‑friendly).
    POST – accepts JSON payload to update/redeem coins.
    """
    user = get_acting_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    if request.method == "POST":
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400

        data = request.get_json()
        action = data.get('action')
        amount = data.get('amount', 0)

        if action not in ('add_points', 'redeem_points'):
            return jsonify({'error': 'Invalid action'}), 400
        if not isinstance(amount, int) or amount <= 0:
            return jsonify({'error': 'Amount must be a positive integer'}), 400

        try:
            if action == 'add_points':
                user.points += amount
                calories_val = amount
                transport_val = 'wallet_add'
            else:  # redeem_points
                if user.points < amount:
                    return jsonify({'error': 'Insufficient points'}), 400
                user.points -= amount
                calories_val = -amount
                transport_val = 'wallet_redeem'

            # Record a simple wallet transaction using DailyLog as a placeholder
            from datetime import datetime
            log = DailyLog(
                user_id=user.id,
                date=datetime.utcnow().date(),
                total=user.points,  # snapshot of current balance
                transport=transport_val,
                calories=calories_val,
            )
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.exception('Wallet update failed')
            return jsonify({'error': 'Internal server error'}), 500

    # Common GET & POST return logic
    lvl, title, prog, thresh = user.get_level_info()
    recent_logs = (
        DailyLog.query.filter_by(user_id=user.id)
        .order_by(DailyLog.date.desc())
        .limit(10)
        .all()
    )

    transactions = []
    for log in recent_logs:
        if log.transport in ('wallet_update', 'wallet_add', 'wallet_redeem'):
            if log.transport == 'wallet_add':
                action_desc = "Added Points"
                amount_val = log.calories
            elif log.transport == 'wallet_redeem':
                action_desc = "Redeemed Points"
                amount_val = log.calories
            else:
                action_desc = "Points Adjustment"
                amount_val = log.calories if log.calories != 0 else 0
        else:
            # Commute activity
            pts = 100
            if log.total <= GREEN_DAY_LIMIT:
                pts += 50
            if log.transport != 'car_solo':
                pts += 100

            mode_map = {
                'walk': 'Commuted by Walking',
                'bicycle': 'Commuted by Bicycle',
                'bus': 'Commuted by Bus',
                'metro': 'Commuted by Metro',
                'car_solo': 'Commuted by Car (Solo)',
            }
            action_desc = mode_map.get(log.transport, f"Logged Activity ({log.transport})")
            amount_val = pts

        transactions.append({
            'action': action_desc,
            'amount': amount_val,
            'timestamp': log.date.isoformat(),
        })

    resp = {
        'balance': user.points,
        'level': lvl,
        'level_title': title,
        'level_progress': prog,
        'level_threshold': thresh,
        'transactions': transactions,
    }
    if request.method == "POST":
        resp['success'] = True

    return jsonify(resp)


# Deprecated: route registration moved to @app.route decorator
# app.add_url_rule(
#     '/api/wallet',
#     view_func=wallet_api,
#     methods=['GET', 'POST'],
#     provide_automatic_options=False,
# )
@app.route('/api/autocomplete')
def autocomplete():
    """Proxy OLA Maps autocomplete — keeps API key off the frontend."""
    q = request.args.get('q', '').strip()
    if len(q) < 3:
        return jsonify([])
    try:
        url = "https://api.olamaps.io/places/v1/autocomplete"
        params = {"input": q, "api_key": OLA_MAPS_KEY, "language": "en"}
        r = requests.get(url, params=params).json()
        predictions = r.get("predictions", [])
        results = []
        for p in predictions:
            loc = p.get("geometry", {}).get("location", {})
            lat, lng = loc.get("lat"), loc.get("lng")
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
    except Exception:
        return jsonify([]), 500


# ── Carbon Calculation ────────────────────────────────────────

def get_grid_carbon_intensity(lat, lon):
    if not ELECTRICITY_MAPS_API_KEY:
        return 0.3, "Fallback (0.3 kg/kWh) - Key missing"

    try:
        url = f"https://api.electricitymaps.com/v3/carbon-intensity/latest?lat={lat}&lon={lon}"
        res = requests.get(url, headers={"auth-token": ELECTRICITY_MAPS_API_KEY}, timeout=5)
        res.raise_for_status()
        intensity_data = res.json()
        carbon_intensity = intensity_data.get("carbonIntensity")
        if carbon_intensity is not None:
            factor = round(carbon_intensity / 1000.0, 3)
            factor = max(0.05, min(1.5, factor))
            return factor, "Electricity Maps API"
        else:
            raise ValueError("carbonIntensity key missing in API response")
    except Exception as e:
        logger.warning("Electricity Maps API failed, falling back to 0.3 kg CO2/kWh: %s", e)
        return 0.3, f"Fallback (0.3 kg/kWh) - Error: {type(e).__name__}"


@app.route('/api/calculate', methods=['POST'])
def calculate_carbon():
    try:
        data = request.json
        food_impact = float(data.get('food', 0))
        elec_hours = float(data.get('electricity', 0))
        transport_key = data.get('transport', 'car_solo')
        manual_dist = data.get('distance_km')
        smart_food_calories = float(data.get('smart_food_calories', 0))

        geo_mode, co2_per_km, mode_label = TRANSPORT_MODES.get(
            transport_key, TRANSPORT_MODES['car_solo']
        )

        d_lat, d_lon = None, None
        if manual_dist is not None:
            dist_km = float(manual_dist)
            commute_co2 = round(dist_km * co2_per_km, 2)
            fastest = cheapest = greenest = None
            
            d_lat = data.get('dest_lat') or data.get('origin_lat')
            d_lon = data.get('dest_lon') or data.get('origin_lon')
            if not d_lat or not d_lon:
                # Fallback to Chennai coordinates if manual entry doesn't supply them
                d_lat, d_lon = 13.0827, 80.2707
        else:
            o_lat, o_lon = data.get('origin_lat'), data.get('origin_lon')
            d_lat, d_lon = data.get('dest_lat'), data.get('dest_lon')

            if not all([o_lat, o_lon, d_lat, d_lon]):
                o_lat, o_lon = geocode(data.get('origin', ''))
                d_lat, d_lon = geocode(data.get('destination', ''))

            if None in (o_lat, o_lon, d_lat, d_lon):
                return jsonify({'success': False, 'error': 'Location not found'}), 400

            with concurrent.futures.ThreadPoolExecutor() as executor:
                sel_f   = executor.submit(get_route_data, o_lat, o_lon, d_lat, d_lon, geo_mode, co2_per_km)
                fast_f  = executor.submit(get_route_data, o_lat, o_lon, d_lat, d_lon, 'driving', 0.171)
                cheap_f = executor.submit(get_route_data, o_lat, o_lon, d_lat, d_lon, 'driving', 0.041)
                green_f = executor.submit(get_route_data, o_lat, o_lon, d_lat, d_lon, 'cycling', 0.0)

                selected_route = sel_f.result()
                fastest = fast_f.result()
                cheapest = cheap_f.result()
                greenest = green_f.result() if (selected_route and selected_route['dist'] <= 15) else cheapest

            dist_km = selected_route['dist'] if selected_route else 0
            commute_co2 = selected_route['co2'] if selected_route else 0

        # Calculate grid intensity dynamically based on location
        grid_factor, grid_source = get_grid_carbon_intensity(d_lat, d_lon)
        elec_co2 = elec_hours * grid_factor
        smart_food_impact = float(data.get('smart_food_co2', 0))
        total = commute_co2 + food_impact + elec_co2 + smart_food_impact

        equivalents = [
            {'emoji': '🍔', 'label': 'Beef burgers',      'value': round(total / 6.0,  1), 'unit': 'burgers'},
            {'emoji': '🚿', 'label': 'Showers',           'value': round(total / 0.5,  1), 'unit': 'mins'},
            {'emoji': '📺', 'label': 'Netflix on big TV', 'value': round(total / 0.097, 1), 'unit': 'hours'},
            {'emoji': '✈️', 'label': 'Flight time',       'value': round(total / 3.37, 2), 'unit': 'hours'},
            {'emoji': '💡', 'label': 'LED bulb on',       'value': round(total / 0.008, 0), 'unit': 'hours'},
            {'emoji': '🌊', 'label': 'Arctic ice melted', 'value': round(total * 3.0,  1), 'unit': 'm²'},
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
            'equivalents': equivalents,
            'grid_factor': grid_factor,
            'grid_source': grid_source
        })
    except Exception as e:
        logger.exception("calculate_carbon failed")
        return jsonify({'success': False, 'error': str(e)}), 500


# ── AI Coach ──────────────────────────────────────────────────

@app.route('/api/coach', methods=['POST'])
def carbon_coach():
    try:
        data = request.json
        username = data.get('username', 'Student')
        transport = data.get('transport_label', 'Car')
        dist_km = data.get('distance_km', 0)
        commute_co2 = data.get('breakdown', {}).get('commute', 0)
        food_co2 = data.get('breakdown', {}).get('food', 0)
        elec_co2 = data.get('breakdown', {}).get('electricity', 0)
        total_co2 = data.get('total', 0)
        eco = data.get('eco_planner', {})
        greenest = eco.get('greenest') or {}
        cheapest = eco.get('cheapest') or {}

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
            raise ValueError("Empty response from Ollama")
        return jsonify({"message": message})

    except Exception as e:
        logger.warning("Ollama coaching failed, using local fallback generator: %s", e)
        
        # Fallback local tip generator
        contribs = [
            ("commute", commute_co2, f"your commute emissions ({commute_co2:.1f} kg CO₂) were your biggest contributor today. Choosing to walk, bike, or take public transit like the bus or metro can significantly lower this!"),
            ("food", food_co2, f"your food footprint ({food_co2:.1f} kg CO₂) represents a major portion of your emissions. Opting for delicious vegetarian or vegan options is one of the most effective ways to lower your impact!"),
            ("electricity", elec_co2, f"your energy use ({elec_co2:.1f} kg CO₂) made up a notable part of your daily footprint. Unplugging devices when not in use and turning off lights can save both energy and carbon.")
        ]
        contribs.sort(key=lambda x: x[1], reverse=True)
        biggest_contributor_text = contribs[0][2]
        
        alternative_text = ""
        if greenest and greenest.get('dist') and greenest.get('co2', 999) < commute_co2:
            alternative_text = f" I noticed you could save carbon by taking a greener route (only {greenest.get('co2')} kg CO₂ for {greenest.get('dist')} km)!"
        elif cheapest and cheapest.get('co2', 999) < commute_co2:
            alternative_text = f" Did you know that taking a shared ride could help you reduce your commute emissions to {cheapest.get('co2')} kg CO₂?"

        fallback_msg = f"Hi {username}! 🌿 Your total carbon footprint today is {total_co2:.1f} kg CO₂. {biggest_contributor_text}{alternative_text} Keep up the great work tracking your impact and making green choices! 🌍"
        return jsonify({"message": fallback_msg})


# ── Smart Food Analysis ───────────────────────────────────────

@app.route('/api/analyze-food-smart', methods=['POST'])
def analyze_food_smart():
    text = ""
    source = "list"

    if 'file' in request.files:
        if not OCR_AVAILABLE:
            return jsonify({'error': 'OCR not available on server'}), 503
        file = request.files['file']
        img = Image.open(file.stream)
        text = pytesseract.image_to_string(img)
        source = "receipt"
    else:
        data = request.json or {}
        text = data.get('text', '')
        source = "list"

    if not text.strip():
        return jsonify({'error': 'No text or image provided'}), 400

    # Food carbon estimates per standard portion (~150g)
    carbon_estimates = {
        'vegan': 0.8, 'salad': 0.9, 'vegetable': 1.0, 'veg': 1.0,
        'paneer': 1.8, 'vegetarian': 1.5,
        'chicken': 2.5, 'fish': 2.3, 'seafood': 2.4,
        'mutton': 4.5, 'lamb': 5.2, 'beef': 5.2,
        'butter chicken': 3.2, 'tandoori': 2.8,
        'biryani': 2.2, 'dal': 1.2, 'curry': 2.0,
        'pizza': 1.8, 'pasta': 1.5, 'burger': 3.0,
        'chaat': 1.5, 'samosa': 1.2, 'dosa': 1.3,
        'thali': 2.0, 'rice': 0.5, 'bread': 0.4,
    }

    items = []
    total_calories = 0
    total_co2 = 0.0

    # Try to query CalorieNinjas API if key is available
    if CALORIENINJAS_API_KEY:
        try:
            url = f"https://api.calorieninjas.com/v1/nutrition?query={requests.utils.quote(text)}"
            res = requests.get(url, headers={'X-Api-Key': CALORIENINJAS_API_KEY}, timeout=10)
            res.raise_for_status()
            api_data = res.json()
            api_items = api_data.get('items', [])
            
            for item in api_items:
                name = item.get('name', 'Unknown Item').title()
                calories = item.get('calories', 0)
                serving_size_g = item.get('serving_size_g', 150)
                
                # Match carbon footprint keyword
                name_lower = name.lower()
                base_co2 = 1.5  # Default fallback
                for kw, val in carbon_estimates.items():
                    if kw in name_lower:
                        base_co2 = val
                        break
                
                # Scale co2 by weight relative to standard 150g serving
                co2_estimate = round(base_co2 * (serving_size_g / 150.0), 2)
                co2_estimate = max(0.1, min(10.0, co2_estimate)) # Cap value
                
                items.append({
                    "name": name,
                    "calories": round(calories),
                    "co2": co2_estimate
                })
                total_calories += calories
                total_co2 += co2_estimate

            if items:
                return jsonify({
                    'items': items,
                    'total_calories': round(total_calories),
                    'total_co2': round(total_co2, 2),
                    'text_extracted': text[:200] + "..." if len(text) > 200 else text,
                    'source': 'calorieninjas'
                })
        except Exception as e:
            logger.warning("CalorieNinjas request failed, falling back: %s", e)

    # Local fallback rule-based parser if CalorieNinjas is unconfigured/fails
    import re
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    for line in lines[:10]: # Limit to top 10 items to prevent overload
        line_lower = line.lower()
        # Ignore total, prices, card info, dates
        if any(w in line_lower for w in ['total', 'price', 'tax', 'date', 'visa', 'card', 'cash', 'gst', 'rs', 'inr']):
            continue
        
        # Simple quantity detection (e.g. "2x Pizza" or "2 Pizza" or "Pasta 1")
        quantity = 1
        qty_match = re.search(r'\b(\d+)\s*(x|qty)?\b', line_lower)
        if qty_match:
            try:
                quantity = int(qty_match.group(1))
            except Exception:
                pass

        # Estimate calories & carbon footprint
        item_calories = 250  # default
        item_co2 = 1.5       # default
        detected_name = line.strip().title()

        matched = False
        for kw, val in carbon_estimates.items():
            if kw in line_lower:
                item_co2 = val
                # Rough calorie estimates based on food type
                if kw in ['burger', 'pizza', 'mutton', 'lamb', 'beef']:
                    item_calories = 500
                elif kw in ['chicken', 'fish', 'seafood', 'butter chicken', 'biryani', 'pasta']:
                    item_calories = 400
                elif kw in ['paneer', 'vegetarian', 'veg', 'curry', 'thali']:
                    item_calories = 300
                elif kw in ['vegan', 'salad', 'vegetable', 'dal', 'samosa', 'dosa', 'chaat']:
                    item_calories = 150
                elif kw in ['rice', 'bread']:
                    item_calories = 200
                matched = True
                break
        
        # Final values scaled by quantity
        final_calories = item_calories * quantity
        final_co2 = round(item_co2 * quantity, 2)
        
        items.append({
            "name": detected_name,
            "calories": final_calories,
            "co2": final_co2
        })
        total_calories += final_calories
        total_co2 += final_co2

    if not items:
        # Absolute fallback if no items could be parsed
        items = [{'name': 'Extracted Meal', 'calories': 350, 'co2': 1.5}]
        total_calories = 350
        total_co2 = 1.5

    return jsonify({
        'items': items,
        'total_calories': round(total_calories),
        'total_co2': round(total_co2, 2),
        'text_extracted': text[:200] + "..." if len(text) > 200 else text,
        'source': 'fallback'
    })


@app.route('/api/ocr-receipt', methods=['POST'])
def ocr_receipt():
    return analyze_food_smart()


# ══════════════════════════════════════════════════════════════
#  SAVE ENTRY (DB-backed)
# ══════════════════════════════════════════════════════════════

@app.route('/api/save-entry', methods=['POST'])
def save_entry():
    try:
        data = request.json
        raw_user = data.get('username', 'Anonymous').strip() or 'Anonymous'
        username = ''.join(c for c in raw_user if c.isalnum() or c in ' ._-')[:50] or 'Anonymous'
        department = data.get('department', 'General').strip()[:50] or 'General'
        total = max(0, min(float(data.get('total', 0)), 500))
        transport = data.get('transport', 'car_solo')
        if transport not in TRANSPORT_MODES:
            transport = 'car_solo'
        food_value = max(0, min(float(data.get('food_value', 1.5)), 100))
        elec_co2 = max(0, min(float(data.get('elec_co2', 0)), 100))
        calories = max(0, min(int(data.get('calories', 0)), 50000))
        today = dt_date.today()

        # Resolve user: prefer authenticated, fallback to name lookup/create
        user = None
        if current_user.is_authenticated:
            user = current_user
        else:
            user = User.query.filter_by(name=username).first()
            if not user:
                user = User(name=username, department=department)
                db.session.add(user)
                db.session.flush()

        user.department = department

        # Create daily log
        log = DailyLog(
            user_id=user.id,
            date=today,
            total=total,
            transport=transport,
            food_value=food_value,
            elec_co2=elec_co2,
            compost=data.get('compost', False),
            solar=data.get('solar', False),
            water_usage=data.get('water_usage'),
            calories=calories,
        )
        db.session.add(log)

        # Award points: 100 per log, +50 if green day
        user.points = (user.points or 0) + 100
        if total <= GREEN_DAY_LIMIT:
            user.points += 50
        # Extra +100 XP if they chose a green/active/shared transportation mode (not car_solo)
        if transport != 'car_solo':
            user.points += 100

        user.total_calories = (user.total_calories or 0) + calories

        # Recompute badges and streak
        db.session.flush()  # ensure log is visible in queries
        all_badges, streak, new_badges = compute_badges_and_streak(user)

        db.session.commit()

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
            'success': True,
            'streak': streak,
            'points': user.points,
            'new_badges': new_badge_details,
            'all_badges': all_badge_details
        })
    except Exception as e:
        db.session.rollback()
        logger.exception("save-entry failed")
        return jsonify({'success': False, 'error': 'An internal error occurred.'}), 500


# ══════════════════════════════════════════════════════════════
#  BADGES / LEADERBOARD / RANKING (DB-backed)
# ══════════════════════════════════════════════════════════════

@app.route('/api/badges/<username>', methods=['GET'])
def get_badges(username):
    try:
        user = User.query.filter_by(name=username).first()
        if not user:
            return jsonify({'streak': 0, 'points': 0, 'badges': []})

        all_badges, streak, _ = compute_badges_and_streak(user)
        db.session.commit()  # persist any new badges found

        badges = [
            {'id': bid, 'emoji': BADGE_DEFS[bid][0],
             'name': BADGE_DEFS[bid][1], 'desc': BADGE_DEFS[bid][2]}
            for bid in all_badges if bid in BADGE_DEFS
        ]
        lvl, title, prog, thresh = user.get_level_info()
        return jsonify({
            'streak': streak,
            'points': user.points or 0,
            'badges': badges,
            'calories': user.total_calories or 0,
            'avg_carbon': user.avg_carbon(),
            'level': lvl,
            'level_title': title,
            'level_progress': prog,
            'level_threshold': thresh,
        })
    except Exception as e:
        return jsonify({'streak': 0, 'badges': [], 'error': str(e)})


@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    dept_filter = request.args.get('dept', '').strip()

    users = User.query.all()
    all_users = []
    for u in users:
        log_count = u.log_count()
        if log_count == 0:
            continue
        entry = {
            'username':   u.name,
            'avg_carbon': u.avg_carbon(),
            'department': u.department or '—',
            'entries':    log_count,
            'streak':     0,  # computed on demand if needed
            'points':     u.points or 0,
            'badges':     [BADGE_DEFS[b][0] for b in u.badge_ids() if b in BADGE_DEFS]
        }
        all_users.append(entry)

    if dept_filter:
        all_users = [u for u in all_users if u['department'] == dept_filter]

    ranked = sorted(all_users, key=lambda x: x['avg_carbon'])
    return jsonify(ranked[:15])


@app.route('/api/award-badge', methods=['POST'])
def award_badge():
    try:
        data = request.json
        username = data.get('username', '').strip()
        badge_id = data.get('badge', '')
        if not username or badge_id not in BADGE_DEFS:
            return jsonify({'success': False}), 400

        user = User.query.filter_by(name=username).first()
        if not user:
            return jsonify({'success': False}), 404

        existing = UserBadge.query.filter_by(user_id=user.id, badge_id=badge_id).first()
        if not existing:
            db.session.add(UserBadge(user_id=user.id, badge_id=badge_id))
            db.session.commit()

        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/redeem-tree', methods=['POST'])
def redeem_tree():
    try:
        data = request.json
        username = data.get('username', '').strip()
        if not username:
            return jsonify({'success': False, 'error': 'No user'}), 400

        user = User.query.filter_by(name=username).first()
        if not user:
            return jsonify({'success': False, 'error': 'Not found'}), 404

        if (user.points or 0) < 5000:
            return jsonify({'success': False, 'error': 'Not enough points (need 5,000)'}), 400

        user.points -= 5000
        new_badge = False
        if not UserBadge.query.filter_by(user_id=user.id, badge_id='tree_planter').first():
            db.session.add(UserBadge(user_id=user.id, badge_id='tree_planter'))
            new_badge = True

        db.session.commit()
        return jsonify({'success': True, 'points': user.points, 'new_badge': new_badge})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


def get_user_streak(user):
    logs = user.daily_logs.order_by(DailyLog.date).all()
    if not logs:
        return 0
    log_dates = sorted({l.date for l in logs}, reverse=True)
    streak = 0
    check = dt_date.today()
    for d in log_dates:
        if d == check:
            day_total = min(l.total for l in logs if l.date == d)
            if day_total <= GREEN_DAY_LIMIT:
                streak += 1
                check = check - timedelta(days=1)
            else:
                break
        elif d < check:
            break
    return streak


@app.route('/api/dept-battle', methods=['GET'])
def dept_battle():
    try:
        users = User.query.all()
        dept_map = {}
        for user in users:
            dept = user.department or 'Other'
            if dept not in dept_map:
                dept_map[dept] = {'total_co2': 0, 'members': 0, 'logs': 0,
                                  'top_streak': 0, 'badges_count': 0}
            d = dept_map[dept]
            d['members'] += 1
            log_count = user.log_count()
            d['logs'] += log_count
            d['total_co2'] += user.avg_carbon()
            d['badges_count'] += user.badges.count()
            
            streak = get_user_streak(user)
            if streak > d['top_streak']:
                d['top_streak'] = streak

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
    except Exception:
        return jsonify([])


@app.route('/api/ranking', methods=['GET'])
def get_ranking():
    RANK_ICONS = [
        (1, "🏆", "text-yellow-500"),
        (2, "🥈", "text-slate-300"),
        (3, "🥉", "text-amber-600"),
    ]
    try:
        users = User.query.all()
        sorted_users = sorted(
            [{'username': u.name, 'avg_carbon': u.avg_carbon(),
              'department': u.department or '—',
              'badges': [BADGE_DEFS[b][0] for b in u.badge_ids() if b in BADGE_DEFS]}
             for u in users if u.log_count() > 0],
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
                'id': rank, 'name': user['username'],
                'badges': user['badges'], 'dept': user['department'],
                'carbon': round(user['avg_carbon'], 2),
                'icon': icon, 'iconColor': icon_color,
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/profile/<username>', methods=['GET'])
def get_profile(username):
    try:
        user = User.query.filter_by(name=username).first()
        if not user:
            return jsonify({'daily_logs': []})
        logs = [l.to_dict() for l in user.daily_logs.order_by(DailyLog.date).all()]
        return jsonify({'daily_logs': logs})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin', methods=['GET'])
def get_admin_stats():
    try:
        users = User.query.all()
        total_logs = 0
        total_co2 = 0
        total_users = len(users)
        green_days = 0

        for user in users:
            logs = user.daily_logs.all()
            total_logs += len(logs)
            total_co2 += sum(l.total for l in logs)
            green_days += sum(1 for l in logs if l.total <= GREEN_DAY_LIMIT)

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
        return jsonify({'error': str(e)}), 500

# ── EVENT MATCHMAKING LOGIC ────────────────────────────────────────

def _events_file_path():
    """Return absolute path to events.json"""
    return os.path.join(os.path.dirname(__file__), 'data', 'events.json')

def _load_events():
    """Load events list from JSON file"""
    path = _events_file_path()
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except Exception:
            return []

def _save_events(events):
    """Write events list back to JSON file"""
    path = _events_file_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=2)

@app.route('/api/events/matchmaker', methods=['POST'])

def matchmaker():
    """Match users who have joined a car‑pool for the same event.
    Request JSON: {"event_id": <int>, "username": <str>}
    Returns list of other participants and estimated shared carbon savings.
    """
    data = request.get_json() or {}
    event_id = data.get('event_id')
    username = (data.get('username') or '').strip()
    if not event_id or not username:
        return jsonify({'success': False, 'error': 'event_id and username required'}), 400

    events = _load_events()
    event = next((e for e in events if e.get('id') == event_id), None)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    attendees = set(event.get('attendees_joined_ride', []))
    attendees.add(username)
    event['attendees_joined_ride'] = list(attendees)
    _save_events(events)

    matched_users = [u for u in attendees if u != username]

    # Simple shared savings calculation – assume a generic distance of 5 km.
    # Solo emission per km = 0.171 kg CO₂, car‑pool emission per km = 0.068 kg CO₂.
    distance_km = 5.0
    solo_co2 = distance_km * 0.171
    carpool_co2 = distance_km * 0.068
    shared_savings = max(0, (solo_co2 - carpool_co2) * len(matched_users))

    return jsonify({
        'success': True,
        'matched_users': matched_users,
        'shared_savings_kg': round(shared_savings, 2),
    })


# ══════════════════════════════════════════════════════════════
#  ECO HUB — Events & News (kept as JSON files, not user data)
# ══════════════════════════════════════════════════════════════

ECOHUB_FILE = "data/chennai_events.json"


def load_ecohub_data():
    try:
        if os.path.exists(ECOHUB_FILE):
            with open(ECOHUB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"events": [], "news": []}


def load_and_refresh_ecohub_data():
    data = load_ecohub_data()
    last_updated_str = data.get("last_updated")
    needs_refresh = True
    
    if last_updated_str:
        try:
            last_updated = datetime.fromisoformat(last_updated_str)
            # Cache for 1 hour
            if datetime.utcnow() - last_updated < timedelta(hours=1):
                needs_refresh = False
        except Exception:
            pass

    if needs_refresh:
        # Purge past events
        today = datetime.today().date()
        filtered_events = []
        for ev in data.get('events', []):
            try:
                ev_date = datetime.strptime(ev.get('date', ''), "%Y-%m-%d").date()
                if ev_date >= today:
                    filtered_events.append(ev)
            except Exception:
                # Retain if it doesn't match standard YYYY-MM-DD format (fallback)
                filtered_events.append(ev)

        # Dynamic template events generator to ensure we always have upcoming events in OMR/Besant Nagar/IITM
        dynamic_templates = [
            {
                "id": "dyn-evt-001",
                "title": "Besant Nagar Beach Cleanup Drive",
                "time": "06:00 AM - 09:00 AM",
                "location": "Besant Nagar Beach, Elliot's Beach, Chennai",
                "description": "Join volunteers for a massive shoreline cleanup. Help remove plastic waste and microplastics from one of Chennai's most iconic beaches. Gloves and bags provided.",
                "category": "cleanup",
                "organizer": "Chennai Coastal Conservation Group",
                "contact_url": "https://example.com/besant-cleanup",
                "emoji": "🏖️",
                "attendees": 187,
                "max_attendees": 300,
                "day_offset": 5,
            },
            {
                "id": "dyn-evt-002",
                "title": "Adyar Eco Park – 1000 Trees Plantation",
                "time": "07:00 AM - 11:00 AM",
                "location": "Adyar Eco Park, Adyar, Chennai",
                "description": "Be part of Chennai's urban reforestation effort! Plant native species like Neem, Peepal, and Banyan. Each sapling absorbs ~22 kg CO₂ per year.",
                "category": "treePlant",
                "organizer": "Green Chennai Foundation",
                "contact_url": "https://example.com/adyar-trees",
                "emoji": "🌳",
                "attendees": 342,
                "max_attendees": 500,
                "day_offset": 6,
            },
            {
                "id": "dyn-evt-003",
                "title": "IIT Madras – Carbon Neutrality Workshop",
                "time": "10:00 AM - 04:00 PM",
                "location": "IC & SR Auditorium, IIT Madras, Chennai",
                "description": "A full-day hands-on workshop on measuring your carbon footprint, understanding emission sources, and building personal action plans.",
                "category": "workshop",
                "organizer": "IIT Madras Sustainability Cell",
                "contact_url": "https://example.com/iitm-workshop",
                "emoji": "🎓",
                "attendees": 89,
                "max_attendees": 150,
                "day_offset": 2,
            },
            {
                "id": "dyn-evt-004",
                "title": "Marina to Mylapore Eco Cycling Rally",
                "time": "05:30 AM - 08:00 AM",
                "location": "Marina Beach Lighthouse (Start Point), Chennai",
                "description": "Ride 12 km from Marina to Mylapore and back! Promote zero-emission transport and win eco-prizes.",
                "category": "ecoRide",
                "organizer": "Pedal Chennai",
                "contact_url": "https://example.com/eco-ride",
                "emoji": "🚲",
                "attendees": 256,
                "max_attendees": 400,
                "day_offset": 10,
            }
        ]

        # Generate future dates for template events
        for t in dynamic_templates:
            event_date = (today + timedelta(days=t["day_offset"])).isoformat()
            existing_ids = {e.get("id") for e in filtered_events}
            if t["id"] not in existing_ids:
                event_copy = t.copy()
                event_copy.pop("day_offset")
                event_copy["date"] = event_date
                filtered_events.append(event_copy)

        data['events'] = filtered_events

        # Refresh live news RSS
        try:
            live_news = fetch_live_news(data)
            if live_news:
                data['news'] = live_news
        except Exception as e:
            logger.warning("Could not refresh live news: %s", e)

        # Update last_updated timestamp and save
        data['last_updated'] = datetime.utcnow().isoformat()
        try:
            os.makedirs(os.path.dirname(ECOHUB_FILE), exist_ok=True)
            with open(ECOHUB_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.exception("Failed to save refreshed EcoHub data: %s", e)

    return data


@app.route('/api/eco-events')
def get_eco_events():
    try:
        data = load_and_refresh_ecohub_data()
        events = data.get("events", [])
        category = request.args.get("category", "").strip().lower()
        if category and category != "all":
            events = [e for e in events if e.get("category", "").lower() == category]
        events.sort(key=lambda e: e.get("date", ""))

        # Add interest counts from DB
        for evt in events:
            evt["interested_count"] = EventInterest.query.filter_by(event_id=evt["id"]).count()

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

            if " - " in title:
                title_parts = title.rsplit(" - ", 1)
                title = title_parts[0]
                if len(title_parts) > 1 and source == "Google News":
                    source = title_parts[1]

            news_items.append({
                "id": link, "title": title, "source": source,
                "date": pubDate, "summary": "Live update from " + source,
                "url": link, "category": "news", "emoji": "📰"
            })

        if news_items:
            return news_items
    except Exception as e:
        logger.warning("RSS fetch failed: %s", e)

    return fallback_data.get("news", [])


@app.route('/api/eco-news')
def get_eco_news():
    try:
        data = load_and_refresh_ecohub_data()
        news = data.get("news", [])
        return jsonify({"news": news, "count": len(news)})
    except Exception as e:
        return jsonify({"news": [], "error": str(e)}), 500


@app.route('/api/eco-events/interest', methods=['POST'])
def toggle_interest():
    try:
        body = request.json
        event_id = body.get("event_id", "")
        username = body.get("username", "").strip()
        if not event_id or not username:
            return jsonify({"success": False, "error": "Missing fields"}), 400

        user = User.query.filter_by(name=username).first()
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404

        existing = EventInterest.query.filter_by(user_id=user.id, event_id=event_id).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
            count = EventInterest.query.filter_by(event_id=event_id).count()
            return jsonify({"success": True, "interested": False, "count": count})
        else:
            db.session.add(EventInterest(user_id=user.id, event_id=event_id))
            db.session.commit()
            count = EventInterest.query.filter_by(event_id=event_id).count()
            return jsonify({"success": True, "interested": True, "count": count})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/eco-events/my-interests/<username>')
def get_my_interests(username):
    try:
        user = User.query.filter_by(name=username).first()
        if not user:
            return jsonify({"interests": []})
        interests = [ei.event_id for ei in user.event_interests.all()]
        return jsonify({"interests": interests})
    except Exception as e:
        return jsonify({"interests": [], "error": str(e)}), 500


# ══════════════════════════════════════════════════════════════
#  STRAVA INTEGRATION
# ══════════════════════════════════════════════════════════════

@app.route('/api/strava/oauth', methods=['GET'])
def strava_oauth():
    url = (f"https://www.strava.com/oauth/authorize?client_id={STRAVA_CLIENT_ID}"
           f"&response_type=code&redirect_uri={STRAVA_REDIRECT_URI}&approval_prompt=force&scope=activity:read_all")
    return redirect(url)


@app.route('/api/strava/callback', methods=['GET'])
def strava_callback():
    code = request.args.get('code')
    error = request.args.get('error')

    if error or not code:
        return redirect('/#activity?strava_error=denied')

    token_url = "https://www.strava.com/oauth/token"
    payload = {
        'client_id': STRAVA_CLIENT_ID,
        'client_secret': STRAVA_CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code'
    }

    try:
        res = requests.post(token_url, data=payload, timeout=10)
    except Exception:
        return redirect('/#activity?strava_error=network')

    if res.status_code == 403:
        return redirect('/#activity?strava_error=athlete_limit')
    if res.status_code != 200:
        return redirect('/#activity?strava_error=token_fail')

    token_data = res.json()
    session['strava_access_token'] = token_data.get('access_token')
    session['strava_refresh_token'] = token_data.get('refresh_token')
    session['strava_expires_at'] = token_data.get('expires_at')

    return redirect('/#activity')


@app.route('/api/strava/sync', methods=['POST'])
def sync_strava():
    access_token = session.get('strava_access_token')
    if not access_token:
        return jsonify({"success": False, "error": "Not authenticated with Strava."}), 401

    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        activities_url = "https://www.strava.com/api/v3/athlete/activities?per_page=15"
        res = requests.get(activities_url, headers=headers)

        if res.status_code != 200:
            return jsonify({"success": False, "error": f"Strava API Error: {res.status_code}"}), 500

        raw_activities = res.json()
        formatted_activities = []

        for act in raw_activities:
            if act.get('type') not in ['Run', 'Ride', 'Walk', 'Hike']:
                continue
            dist_km = act.get('distance', 0) / 1000.0
            moving_time_min = act.get('moving_time', 0) // 60
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

        rewarded_points = int(sum(a['carbon_saved'] * 50 for a in formatted_activities))

        data = request.json
        username = data.get('username', 'Anonymous').strip() if data else 'Anonymous'
        if username != 'Anonymous':
            user = User.query.filter_by(name=username).first()
            if user:
                user.points = (user.points or 0) + rewarded_points
                db.session.commit()

        return jsonify({"success": True, "activities": formatted_activities, "rewarded_points": rewarded_points})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/strava/demo', methods=['GET'])
def strava_demo_activities():
    demo_activities = [
        {
            "id": "demo_1", "type": "Ride",
            "name": "Morning Campus Cycle — Adyar to CEG",
            "distance_km": 6.4, "moving_time_min": 22,
            "date": "2026-04-27", "carbon_saved": 1.3,
            "polyline": "celkA}ekxMyMoCwDgAmCkAiCoAiEqBaDuAuC_B{@e@wBcBgByAeBsBkA}AeAqB{@sBk@wCm@sDi@{DY_EK_EBcEVkDd@wCr@}Bz@{BdAkBjAaBpAoArAiAxAeA|Ai@hBg@hBUnBK~BBjBP~ATzAb@xAf@rAp@nAv@fA|@dAbA~@fAx@lAl@rAf@xAXjBNjBFjBE`BSrBa@nBo@~Ay@pAaAjAcA~@kAt@oAj@sAf@wAVwALwAB{AK{AWoAa@kAm@_A{@s@gAc@mAU_BA_BLyAZwAd@mAt@gA~@gAdAcAxAy@~Ai@lBY~B"
        },
        {
            "id": "demo_2", "type": "Run",
            "name": "Besant Nagar Beach Sunset Run",
            "distance_km": 4.2, "moving_time_min": 28,
            "date": "2026-04-26", "carbon_saved": 0.9,
            "polyline": "s_lkAqokxMbA{GXsCLkCFoCEoCUmCe@iCm@}Bw@uBeAeBkAiBqAyAuAmAyA_A{Am@wAY}AEwANsAb@oAv@gAdA}@nAq@~Ae@lBSxBAhBPrBf@|Bz@nBbAnBhAvAlAjAbBbAxBx@dCf@vCNhCGnCa@rCs@nCaAlCkA`CuAxBwA|AyAnA{AbAyAn@yA^yAHwAUuAg@sAu@kA_AeAmAy@_Bk@eBWgBDcBXaBj@_Bz@yAjAqAvAiA`BaAjBu@xBe@hCQvCAhCNvCb@jCr@~B~@pBjAfBxArAvA~@xAd@zAH"
        },
        {
            "id": "demo_3", "type": "Walk",
            "name": "IIT Madras Deer Park Morning Walk",
            "distance_km": 2.1, "moving_time_min": 35,
            "date": "2026-04-25", "carbon_saved": 0.4,
            "polyline": "qblkAickxMcAyAs@{Ae@oBUoCEqCJsCZsCf@kCz@_C~@yCjA_CjAyBhAyBhA_CbAoCr@sCd@sCR_DE_Da@oCu@mCiAaCyAcBwAkAuAy@yAe@sAQuADuA\\oAn@iAz@}@jAi@xAQnABjATdAj@rAz@bAfAj@pAT`BB`BOfBe@`BcA"
        },
        {
            "id": "demo_4", "type": "Ride",
            "name": "ECR Weekend Coastal Ride",
            "distance_km": 15.8, "moving_time_min": 48,
            "date": "2026-04-24", "carbon_saved": 3.3,
            "polyline": "celkA}ekxMaBcDoAqCcAcC{@yBwAqC}AeCiBoBqBuAsCiAiC{@yCo@}Cc@sDUkDCoDJoDX}Cb@gCt@aCdAqBnAkB~AcBhByA`CgAxCu@tC]rCIxCHhD\\bDh@xCx@jCdAlCrAhCjAbCnA`CnA`CrA`CdAhCx@pC`AdCjAjCrAnBxAhBpA|AvAbBnA|BfAjCr@xCb@dDNhDB~CC~CUhDi@zCw@fCaAnBkAjBsAzAyAnA_BbAmB~@iB~@yBlAaCfAeCdAmCh@oCVwCB"
        },
        {
            "id": "demo_5", "type": "Run",
            "name": "Guindy National Park Trail",
            "distance_km": 3.5, "moving_time_min": 24,
            "date": "2026-04-23", "carbon_saved": 0.7,
            "polyline": "yalkA_ckxM_AmBo@oCYsCAsCPqCd@oCr@kC`AiClA_CxAuBhBoBxBkBdCaBlCsBdCyBnBcCr@oCRqCMqCg@oCaAiCsA}BgBqBwBcBaCo@aCU_CE_CZkCp@aCdAyCdAaCpA}BxAyBbBoBhBgBfBeBdByAbBuAbBkAbBiAxBkA"
        }
    ]
    return jsonify({"success": True, "activities": demo_activities, "is_demo": True})


# ══════════════════════════════════════════════════════════════
#  LIVE CHAT & FRIEND SYNC ENGINE (Step 1)
# ══════════════════════════════════════════════════════════════

CHATS_FILE = "data/chats.json"

def load_chats():
    if os.path.exists(CHATS_FILE):
        try:
            with open(CHATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load chats: %s", e)
    return []

def save_chat(msg):
    chats = load_chats()
    chats.append(msg)
    try:
        os.makedirs(os.path.dirname(CHATS_FILE), exist_ok=True)
        with open(CHATS_FILE, "w", encoding="utf-8") as f:
            json.dump(chats, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("Failed to save chat message: %s", e)

@app.route('/api/chats', methods=['GET'])
def get_chats():
    user = get_acting_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    chats = load_chats()
    user_chats = [c for c in chats if c['sender'] == user.name or c['recipient'] == user.name]
    return jsonify(user_chats)

@app.route('/api/chat/users', methods=['GET'])
def get_chat_users():
    user = get_acting_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    db_users = User.query.filter(User.name != user.name).all()
    chat_users = [
        {'username': u.name, 'department': u.department, 'avatar_url': u.avatar_url}
        for u in db_users
    ]
    
    if not chat_users:
        try:
            with open("data/leaderboard.json", "r", encoding="utf-8") as f:
                lb_data = json.load(f)
                for name, info in lb_data.items():
                    if name != user.name and name not in [u['username'] for u in chat_users]:
                        chat_users.append({
                            'username': name,
                            'department': info.get('department', 'General'),
                            'avatar_url': None
                        })
        except Exception:
            pass
            
    return jsonify(chat_users)

@socketio.on('register')
def handle_register(data):
    username = data.get('username')
    if username:
        join_room(username)
        logger.info(f"Socket registered for user: {username} in room: {username}")

@socketio.on('send_message')
def handle_send_message(data):
    sender = data.get('sender')
    recipient = data.get('recipient')
    text = data.get('text')
    if not sender or not recipient or not text:
        return
    
    timestamp = datetime.utcnow().isoformat() + 'Z'
    message = {
        'sender': sender,
        'recipient': recipient,
        'text': text,
        'timestamp': timestamp
    }
    
    save_chat(message)
    
    emit('receive_message', message, to=recipient)
    emit('receive_message', message, to=sender)


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        logger.info("Database tables created/verified.")

    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.environ.get("PORT", 5000))

    logger.info("Starting Socket.IO server on port %s", port)
    socketio.run(app, host='0.0.0.0', port=port, debug=debug_mode, allow_unsafe_werkzeug=True)
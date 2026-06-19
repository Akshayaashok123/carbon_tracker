"""
Google OAuth 2.0 authentication blueprint for EcoTracker.
Uses Authlib for a clean, secure OAuth flow.
"""
import logging
from flask import Blueprint, redirect, url_for, session, request, jsonify, current_app
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
from models import db, User

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)
login_manager = LoginManager()
oauth = OAuth()


def init_auth(app):
    """Initialize authentication: Flask-Login + Google OAuth."""
    login_manager.init_app(app)
    login_manager.login_view = "auth.login_page"

    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    app.register_blueprint(auth_bp)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@login_manager.unauthorized_handler
def unauthorized():
    """Return 401 JSON for API calls, redirect for page loads."""
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Authentication required"}), 401
    return redirect(url_for("auth.login_page"))


# ── Routes ────────────────────────────────────────────────────


@auth_bp.route("/auth/google")
def google_login():
    """Start Google OAuth flow. Accepts optional ?dept= parameter."""
    dept = request.args.get("dept", "General")
    session["pending_dept"] = dept

    redirect_uri = url_for("auth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/auth/google/callback")
def google_callback():
    """Handle Google OAuth callback — create or find user, start session."""
    try:
        token = oauth.google.authorize_access_token()
        user_info = token.get("userinfo")
        if not user_info:
            user_info = oauth.google.userinfo()

        google_id = user_info.get("sub")
        email = user_info.get("email", "")
        name = user_info.get("name", email.split("@")[0])
        avatar = user_info.get("picture", "")
        dept = session.pop("pending_dept", "General")

        # Find existing user or create new one
        user = User.query.filter_by(google_id=google_id).first()
        if not user:
            user = User.query.filter_by(email=email).first()

        if user:
            # Update profile on each login
            user.name = name
            user.avatar_url = avatar
            if user.department == "General" and dept != "General":
                user.department = dept
        else:
            user = User(
                google_id=google_id,
                email=email,
                name=name,
                department=dept,
                avatar_url=avatar,
            )
            db.session.add(user)

        db.session.commit()
        login_user(user, remember=True)
        logger.info("User logged in: %s (%s)", name, email)

        return redirect("/?logged_in=1")

    except Exception as e:
        logger.exception("Google OAuth callback failed")
        return redirect("/?auth_error=1")


@auth_bp.route("/auth/logout", methods=["POST"])
def logout():
    """Log out the current user."""
    logout_user()
    session.clear()
    return jsonify({"success": True})


@auth_bp.route("/api/me")
def get_current_user():
    """
    Return the logged-in user's profile.
    Called by the frontend on page load to detect auth state.
    """
    if current_user.is_authenticated:
        user = current_user
        return jsonify({
            "authenticated": True,
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "department": user.department,
                "avatar_url": user.avatar_url,
                "points": user.points,
                "total_calories": user.total_calories,
            },
        })
    return jsonify({"authenticated": False})


@auth_bp.route("/api/update-profile", methods=["POST"])
@login_required
def update_profile():
    """Update the current user's department (and optionally name)."""
    try:
        data = request.json or {}
        dept = data.get("department", "").strip()[:50]
        if dept:
            current_user.department = dept
        name = data.get("name", "").strip()[:100]
        if name:
            current_user.name = name
        db.session.commit()
        return jsonify({"success": True, "user": current_user.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


# ── Dev-mode bypass (no Google credentials) ───────────────────

@auth_bp.route("/auth/dev-login", methods=["POST"])
def dev_login():
    """
    Simple name-based login for local development when Google OAuth
    credentials are not configured. Disabled in production.
    """
    if current_app.config.get("GOOGLE_CLIENT_ID"):
        return jsonify({"success": False, "error": "Use Google login"}), 403

    data = request.json or {}
    name = data.get("name", "").strip()[:100]
    dept = data.get("department", "General").strip()[:50]

    if not name:
        return jsonify({"success": False, "error": "Name is required"}), 400

    # Find or create dev user by name
    user = User.query.filter_by(name=name).first()
    if not user:
        user = User(name=name, department=dept)
        db.session.add(user)
        db.session.commit()
    elif dept and dept != "General":
        user.department = dept
        db.session.commit()

    login_user(user, remember=True)
    return jsonify({"success": True, "user": user.to_dict()})


# ── Privacy / Data Export ─────────────────────────────────────

@auth_bp.route("/api/export-my-data")
@login_required
def export_my_data():
    """GDPR-style data export — returns all of the user's data as JSON."""
    user = current_user
    logs = [l.to_dict() for l in user.daily_logs.all()]
    badges = [b.badge_id for b in user.badges.all()]
    interests = [ei.event_id for ei in user.event_interests.all()]

    return jsonify({
        "profile": user.to_dict(),
        "daily_logs": logs,
        "badges": badges,
        "event_interests": interests,
    })


@auth_bp.route("/api/delete-account", methods=["POST"])
@login_required
def delete_account():
    """Permanently delete the current user's account and all associated data."""
    try:
        user = current_user
        logger.info("Account deletion requested: %s (%s)", user.name, user.email)
        db.session.delete(user)
        db.session.commit()
        logout_user()
        session.clear()
        return jsonify({"success": True, "message": "Account and all data deleted."})
    except Exception as e:
        db.session.rollback()
        logger.exception("Account deletion failed")
        return jsonify({"success": False, "error": str(e)}), 500

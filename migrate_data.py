"""
Migrate existing JSON data (leaderboard.json) into the new PostgreSQL/SQLite database.

Run this ONCE after setting up the database:
    python migrate_data.py

It will:
  1. Read data/leaderboard.json
  2. Create User, DailyLog, and UserBadge records for every existing user
  3. Print a summary of migrated records
"""
import json
import os
import sys
from datetime import date as dt_date, datetime

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from flask import Flask
from config import Config
from models import db, User, DailyLog, UserBadge

LEADERBOARD_FILE = "data/leaderboard.json"


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    return app


def migrate():
    app = create_app()

    with app.app_context():
        # Create tables
        db.create_all()

        if not os.path.exists(LEADERBOARD_FILE):
            print(f"⚠️  {LEADERBOARD_FILE} not found — nothing to migrate.")
            return

        with open(LEADERBOARD_FILE, "r") as f:
            board = json.load(f)

        if not board:
            print("⚠️  leaderboard.json is empty — nothing to migrate.")
            return

        user_count = 0
        log_count = 0
        badge_count = 0

        for username, data in board.items():
            # Skip if user already exists (idempotent migration)
            existing = User.query.filter_by(name=username).first()
            if existing:
                print(f"  ⏭  User '{username}' already exists — skipping.")
                continue

            user = User(
                name=username,
                department=data.get("department", "General"),
                points=data.get("points", 0),
                total_calories=data.get("total_calories", 0),
            )
            db.session.add(user)
            db.session.flush()  # Get user.id

            # Migrate daily logs
            for log_entry in data.get("daily_logs", []):
                try:
                    log_date = dt_date.fromisoformat(log_entry["date"])
                except (KeyError, ValueError):
                    continue

                log = DailyLog(
                    user_id=user.id,
                    date=log_date,
                    total=log_entry.get("total", 0),
                    transport=log_entry.get("transport", "car_solo"),
                    food_value=log_entry.get("food_value", 1.5),
                    elec_co2=log_entry.get("elec_co2", 0),
                    compost=log_entry.get("compost", False),
                    solar=log_entry.get("solar", False),
                    water_usage=log_entry.get("water_usage"),
                    calories=log_entry.get("calories", 0),
                )
                db.session.add(log)
                log_count += 1

            # Migrate badges
            for badge_id in data.get("badges", []):
                badge = UserBadge(user_id=user.id, badge_id=badge_id)
                db.session.add(badge)
                badge_count += 1

            user_count += 1
            print(f"  ✅ Migrated '{username}' — "
                  f"{len(data.get('daily_logs', []))} logs, "
                  f"{len(data.get('badges', []))} badges")

        db.session.commit()

        print(f"\n🎉 Migration complete!")
        print(f"   Users:  {user_count}")
        print(f"   Logs:   {log_count}")
        print(f"   Badges: {badge_count}")


if __name__ == "__main__":
    migrate()

"""
SQLAlchemy database models for EcoTracker.
Replaces the JSON file-based storage with proper relational tables.
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """
    A registered user.  Supports Google OAuth and legacy name-based login.
    """
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    email = db.Column(db.String(255), unique=True, nullable=True)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100), default="General")
    avatar_url = db.Column(db.String(500), nullable=True)
    points = db.Column(db.Integer, default=0)
    total_calories = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    daily_logs = db.relationship(
        "DailyLog", backref="user", lazy="dynamic",
        cascade="all, delete-orphan", order_by="DailyLog.date"
    )
    badges = db.relationship(
        "UserBadge", backref="user", lazy="dynamic",
        cascade="all, delete-orphan"
    )
    event_interests = db.relationship(
        "EventInterest", backref="user", lazy="dynamic",
        cascade="all, delete-orphan"
    )

    def badge_ids(self):
        """Return a list of earned badge ID strings."""
        return [b.badge_id for b in self.badges.all()]

    def avg_carbon(self):
        """Average total CO₂ across all daily logs."""
        logs = self.daily_logs.all()
        if not logs:
            return 0.0
        return round(sum(l.total for l in logs) / len(logs), 2)

    def log_count(self):
        return self.daily_logs.count()

    def to_dict(self):
        """Serialize for API responses."""
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "department": self.department,
            "avatar_url": self.avatar_url,
            "points": self.points,
            "total_calories": self.total_calories,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<User {self.name!r}>"


class DailyLog(db.Model):
    """
    One carbon-footprint entry per user per day.
    """
    __tablename__ = "daily_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    date = db.Column(db.Date, nullable=False)
    total = db.Column(db.Float, nullable=False)
    transport = db.Column(db.String(50), default="car_solo")
    food_value = db.Column(db.Float, default=1.5)
    elec_co2 = db.Column(db.Float, default=0.0)
    compost = db.Column(db.Boolean, default=False)
    solar = db.Column(db.Boolean, default=False)
    water_usage = db.Column(db.Float, nullable=True)
    calories = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index("idx_user_date", "user_id", "date"),
    )

    def to_dict(self):
        return {
            "date": self.date.isoformat(),
            "total": self.total,
            "transport": self.transport,
            "food_value": self.food_value,
            "elec_co2": self.elec_co2,
            "compost": self.compost,
            "solar": self.solar,
            "water_usage": self.water_usage,
            "calories": self.calories,
        }

    def __repr__(self):
        return f"<DailyLog user={self.user_id} date={self.date} total={self.total}>"


class UserBadge(db.Model):
    """
    Tracks which badges a user has earned and when.
    """
    __tablename__ = "user_badges"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    badge_id = db.Column(db.String(50), nullable=False)
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),
    )

    def __repr__(self):
        return f"<UserBadge user={self.user_id} badge={self.badge_id!r}>"


class EventInterest(db.Model):
    """
    Tracks user interest in eco-hub events.
    """
    __tablename__ = "event_interests"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event_id = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("user_id", "event_id", name="uq_user_event"),
    )

    def __repr__(self):
        return f"<EventInterest user={self.user_id} event={self.event_id!r}>"

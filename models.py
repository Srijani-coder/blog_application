from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date

db = SQLAlchemy()

# =========================
# USER
# =========================
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    is_admin = db.Column(db.Boolean, default=True, nullable=False)


# =========================
# POST
# =========================
class Post(db.Model):
    __tablename__ = "posts"
    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(240), unique=True, nullable=False)

    content = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    image_path = db.Column(db.String(500), nullable=True)
    video_path = db.Column(db.String(500), nullable=True)

    publish_date = db.Column(db.Date, default=date.today, nullable=False)

    # Relationship
    comments = db.relationship(
        "Comment",
        backref="post",
        lazy="dynamic",
        cascade="all, delete-orphan"
    )

    def is_today(self):
        return self.publish_date == date.today()


# =========================
# COMMENT
# =========================
class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)

    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False, index=True)

    # Public commenter (no login)
    name = db.Column(db.String(80), nullable=False)
    text = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


# =========================================================
# ✅ NEW: ANALYTICS MODELS (REQUIRED FOR YOUR APP.PY)
# =========================================================

# -------------------------
# POST ANALYTICS (AGGREGATE)
# -------------------------
class PostAnalytics(db.Model):
    __tablename__ = "post_analytics"

    id = db.Column(db.Integer, primary_key=True)

    post_id = db.Column(
        db.Integer,
        db.ForeignKey("posts.id"),
        unique=True,
        nullable=False,
        index=True
    )

    views = db.Column(db.Integer, default=0, nullable=False)
    likes = db.Column(db.Integer, default=0, nullable=False)
    shares = db.Column(db.Integer, default=0, nullable=False)

    # Relationship
    post = db.relationship("Post", backref=db.backref("analytics", uselist=False))


# -------------------------
# VIEW SESSION (USER SESSION TRACKING)
# -------------------------
class ViewSession(db.Model):
    __tablename__ = "view_sessions"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(120))

    post_id = db.Column(
        db.Integer,
        db.ForeignKey("posts.id"),
        nullable=False,
        index=True
    )

    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Duration in seconds
    duration = db.Column(db.Float, nullable=True)

    # Relationship
    post = db.relationship("Post", backref="view_sessions")


# -------------------------
# SHARE EVENTS (PLATFORM TRACKING)
# -------------------------
class ShareEvent(db.Model):
    __tablename__ = "share_events"

    id = db.Column(db.Integer, primary_key=True)

    post_id = db.Column(
        db.Integer,
        db.ForeignKey("posts.id"),
        nullable=False,
        index=True
    )

    platform = db.Column(db.String(50), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    post = db.relationship("Post", backref="share_events")
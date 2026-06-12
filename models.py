from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=True, nullable=False)


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

    comments = db.relationship(
        "Comment",
        backref="post",
        lazy="dynamic",
        cascade="all, delete-orphan"
    )

    analytics = db.relationship(
        "PostAnalytics",
        backref="post",
        uselist=False,
        cascade="all, delete-orphan"
    )

    view_sessions = db.relationship(
        "ViewSession",
        backref="post",
        lazy=True,
        cascade="all, delete-orphan"
    )

    share_events = db.relationship(
        "ShareEvent",
        backref="post",
        lazy=True,
        cascade="all, delete-orphan"
    )

    link_clicks = db.relationship(
        "LinkClick",
        backref="post",
        lazy=True,
        cascade="all, delete-orphan"
    )

    summary_feedback = db.relationship(
        "SummaryFeedback",
        backref="post",
        lazy=True,
        cascade="all, delete-orphan"
    )

    def is_today(self):
        return self.publish_date == date.today()


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)

    post_id = db.Column(
        db.Integer,
        db.ForeignKey("posts.id"),
        nullable=False,
        index=True
    )

    name = db.Column(db.String(80), nullable=False)
    text = db.Column(db.Text, nullable=False)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )


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


class ViewSession(db.Model):
    __tablename__ = "view_sessions"

    id = db.Column(db.Integer, primary_key=True)

    device_id = db.Column(db.String(120), nullable=True)

    post_id = db.Column(
        db.Integer,
        db.ForeignKey("posts.id"),
        nullable=False,
        index=True
    )

    started_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    duration = db.Column(db.Float, nullable=True)


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

    device_id = db.Column(db.String(120), nullable=True)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )


class LinkClick(db.Model):
    __tablename__ = "link_clicks"

    id = db.Column(db.Integer, primary_key=True)

    post_id = db.Column(
        db.Integer,
        db.ForeignKey("posts.id"),
        nullable=False,
        index=True
    )

    clicked_url = db.Column(db.Text, nullable=False)
    link_text = db.Column(db.String(300), nullable=True)
    device_id = db.Column(db.String(120), nullable=True, index=True)
    ip_address = db.Column(db.String(80), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )


class SummaryFeedback(db.Model):
    __tablename__ = "summary_feedback"

    id = db.Column(db.Integer, primary_key=True)

    post_id = db.Column(
        db.Integer,
        db.ForeignKey("posts.id"),
        nullable=False,
        index=True
    )

    user_prompt = db.Column(db.Text, nullable=True)

    summary_a = db.Column(db.Text, nullable=True)
    summary_b = db.Column(db.Text, nullable=True)

    selected = db.Column(db.String(1), nullable=False)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )
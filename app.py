import os
import re
import smtplib
from email.message import EmailMessage
from datetime import date, datetime, timedelta
from dotenv import load_dotenv
from models import SummaryFeedback

load_dotenv()

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_file
)
from flask_login import (
    LoginManager, login_user, login_required, logout_user
)
from werkzeug.security import generate_password_hash, check_password_hash

from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

import cloudinary
import cloudinary.uploader

from docx import Document
from striprtf.striprtf import rtf_to_text

from config import Config
from models import db, User, Post, Comment, PostAnalytics, ViewSession, ShareEvent, LinkClick
from chatbot import blog_chatbot_reply


COMMENTS_PAGE_SIZE = 10
MAX_DB_MB = 1000  # 1GB


# ✅ CLOUDINARY (uses CLOUDINARY_URL automatically)
cloudinary.config(secure=True)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = "admin_login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    with app.app_context():
        db.create_all()
        ensure_default_admin()

    # =========================
    # HOME
    # =========================
    @app.get("/")
    def home():
        today = date.today()
        seven_days_ago = today - timedelta(days=7)

        todays_post = (
            Post.query
            .filter(Post.publish_date == today)
            .order_by(Post.created_at.desc())
            .first()
        )

        recent_posts = (
            Post.query
            .filter(Post.publish_date >= seven_days_ago)
            .filter(Post.publish_date != today)
            .order_by(Post.publish_date.desc())
            .limit(6)
            .all()
        )

        todays_comments = []
        todays_comment_count = 0

        if todays_post:
            todays_comment_count = todays_post.comments.count()
            todays_comments = (
                todays_post.comments
                .order_by(Comment.created_at.desc())
                .limit(COMMENTS_PAGE_SIZE)
                .all()
            )

        return render_template(
            "home.html",
            todays_post=todays_post,
            recent_posts=recent_posts,
            todays_comments=todays_comments,
            todays_comment_count=todays_comment_count,
            comments_page_size=COMMENTS_PAGE_SIZE
        )

    # =========================
    # POSTS
    # =========================
    @app.get("/posts")
    def posts():
        posts = Post.query.order_by(Post.publish_date.desc()).all()
        return render_template("posts.html", posts=posts)

    # =========================
    # POST DETAIL
    # =========================
    @app.get("/post/<slug>")
    def post_detail(slug):
        post = Post.query.filter_by(slug=slug).first_or_404()

        comment_count = post.comments.count()

        initial_comments = (
            post.comments
            .order_by(Comment.created_at.desc())
            .limit(COMMENTS_PAGE_SIZE)
            .all()
        )

        return render_template(
            "post.html",
            post=post,
            initial_comments=initial_comments,
            comment_count=comment_count,
            comments_page_size=COMMENTS_PAGE_SIZE
        )

    # =========================
    # ADD COMMENT
    # =========================
    @app.post("/post/<slug>/comment")
    def add_comment(slug):
        post = Post.query.filter_by(slug=slug).first_or_404()

        name = request.form.get("name", "").strip()
        text = request.form.get("text", "").strip()

        if not name or not text:
            flash("Fill all fields", "error")
            return redirect(url_for("post_detail", slug=slug))

        db.session.add(Comment(post_id=post.id, name=name, text=text))
        db.session.commit()

        flash("Comment added!", "success")
        return redirect(url_for("post_detail", slug=slug))

    # =========================
    # ADMIN LOGIN
    # =========================
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "POST":
            user = User.query.filter_by(username=request.form["username"]).first()

            if user and check_password_hash(user.password_hash, request.form["password"]):
                login_user(user)
                return redirect(url_for("admin_dashboard"))

            flash("Invalid credentials", "error")

        return render_template("admin_login.html")

    @app.get("/admin/logout")
    @login_required
    def admin_logout():
        logout_user()
        flash("Logged out", "success")
        return redirect(url_for("home"))

    # =========================
    # ADMIN DASHBOARD
    # =========================
    @app.get("/admin")
    @login_required
    def admin_dashboard():
        posts = Post.query.order_by(Post.created_at.desc()).all()
        return render_template("admin_posts.html", posts=posts)

    # =========================
    # CREATE POST (🔥 UPGRADED)
    # =========================
    @app.route("/admin/new", methods=["GET", "POST"])
    @login_required
    def new_post():
        if request.method == "POST":

            title = request.form["title"]
            content = request.form.get("content", "")

            # DOC upload
            docfile = request.files.get("docfile")
            if docfile and docfile.filename:
                content = extract_rich_content(docfile)

            if not content:
                flash("Provide content or upload a document", "error")
                return redirect(url_for("new_post"))

            # ✅ FIX LIST STRUCTURE HERE
            content = wrap_lists(content)

            image_url = None
            video_url = None

            # IMAGE upload (optimized)
            image = request.files.get("image")
            if image and image.filename:
                res = cloudinary.uploader.upload(
                    image,
                    folder="statsdash/images",
                    resource_type="image",
                    transformation=[
                        {"quality": "auto"},
                        {"fetch_format": "auto"}
                    ]
                )
                image_url = res["secure_url"]

            # VIDEO upload
            video = request.files.get("video")
            if video and video.filename:
                res = cloudinary.uploader.upload(
                    video,
                    folder="statsdash/videos",
                    resource_type="video"
                )
                video_url = res["secure_url"]

            slug = make_unique_slug(title)

            post = Post(
                title=title,
                slug=slug,
                content=content,
                image_path=image_url,
                video_path=video_url,
                publish_date=date.today()
            )

            try:
                db.session.add(post)
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("Slug conflict", "error")
                return redirect(url_for("new_post"))

            manage_db_size()

            flash("Post created!", "success")
            return redirect(url_for("admin_dashboard"))

        return render_template("admin_new_post.html")

    @app.get("/admin/download/<int:id>")
    @login_required
    def download_post(id):
        post = Post.query.get_or_404(id)

        path = os.path.join(os.getcwd(), f"{post.slug}.txt")

        with open(path, "w", encoding="utf-8") as f:

            f.write(post.content)

        return send_file(path, as_attachment=True)

    # =========================
    # ANALYTICS
    # =========================
    @app.post("/track/view/<slug>")
    def track_view(slug):
        post = Post.query.filter_by(slug=slug).first_or_404()

        data = request.get_json()
        device_id = data.get("device_id")

        analytics = PostAnalytics.query.filter_by(post_id=post.id).first()
        if not analytics:
            analytics = PostAnalytics(post_id=post.id)
            db.session.add(analytics)

        # ✅ Unique view per device per day
        existing = ViewSession.query.filter_by(
            post_id=post.id,
            device_id=device_id
            ).first()

        if not existing:
            analytics.views += 1

        session = ViewSession(post_id=post.id, device_id=device_id)

        db.session.add(session)
        db.session.commit()

        return jsonify({"session_id": session.id})

    @app.post("/track/time")
    def track_time():
        data = request.get_json()

        session = ViewSession.query.get(data.get("session_id"))
        if session:
            session.duration = data.get("duration", 0)
            db.session.commit()

        return jsonify({"status": "ok"})

    @app.post("/track/like/<slug>")
    def like_post(slug):
        post = Post.query.filter_by(slug=slug).first_or_404()

        data = request.get_json()
        device_id = data.get("device_id")

        analytics = PostAnalytics.query.filter_by(post_id=post.id).first()
        if not analytics:
            analytics = PostAnalytics(post_id=post.id)
            db.session.add(analytics)

        existing = ShareEvent.query.filter_by(
            post_id=post.id,
            platform="like",
            device_id=device_id
           ).first()
        if not existing:
            analytics.likes += 1

            db.session.add(ShareEvent(
                post_id=post.id,
                platform="like",
                device_id=device_id
            ))
        db.session.commit()

        return jsonify({"likes": analytics.likes})

    @app.post("/track/share/<slug>")

    def share_post(slug):
        post = Post.query.filter_by(slug=slug).first_or_404()

        data = request.get_json()
        platform = data.get("platform")
        device_id = data.get("device_id")

        analytics = PostAnalytics.query.filter_by(post_id=post.id).first()

        if not analytics:
            analytics = PostAnalytics(post_id=post.id)
            db.session.add(analytics)
        
        analytics.shares += 1

        db.session.add(ShareEvent(
            post_id=post.id,
            platform=platform,
            device_id=device_id
        ))

        db.session.commit()

        return jsonify({"shares": analytics.shares})

    @app.post("/track/link-click/<slug>")
    def track_link_click(slug):
        post = Post.query.filter_by(slug=slug).first_or_404()

        data = request.get_json() or {}
        clicked_url = (data.get("url") or "").strip()
        link_text = (data.get("link_text") or "").strip()[:300]
        device_id = (data.get("device_id") or "").strip()

        if not clicked_url:
            return jsonify({"error": "Missing clicked link URL"}), 400

        click = LinkClick(
            post_id=post.id,
            clicked_url=clicked_url,
            link_text=link_text,
            device_id=device_id,
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
            user_agent=request.headers.get("User-Agent", "")[:500]
        )
        db.session.add(click)
        db.session.commit()

        total_clicks = LinkClick.query.filter_by(clicked_url=clicked_url).count()
        unique_users = (
            db.session.query(func.count(func.distinct(LinkClick.device_id)))
            .filter(LinkClick.clicked_url == clicked_url)
            .filter(LinkClick.device_id.isnot(None))
            .filter(LinkClick.device_id != "")
            .scalar() or 0
        )
        post_clicks = LinkClick.query.filter_by(post_id=post.id, clicked_url=clicked_url).count()

        send_link_click_email(
            app,
            post=post,
            clicked_url=clicked_url,
            link_text=link_text,
            device_id=device_id,
            total_clicks=total_clicks,
            unique_users=unique_users,
            post_clicks=post_clicks
        )

        return jsonify({
            "status": "ok",
            "clicked_url": clicked_url,
            "total_clicks": total_clicks,
            "unique_users": unique_users,
            "post_clicks": post_clicks
        })

    # =========================
    # ANALYTICS DASHBOARD (FIX)
    # =========================
    @app.get("/admin/analytics")
    @login_required
    def analytics_dashboard():

        data = db.session.query(
            Post.id,
            Post.title,
            func.coalesce(PostAnalytics.views, 0),
            func.coalesce(PostAnalytics.likes, 0),
            func.coalesce(PostAnalytics.shares, 0),
            func.avg(ViewSession.duration),
            func.count(func.distinct(LinkClick.id)),
            func.count(func.distinct(LinkClick.device_id))
        ).outerjoin(PostAnalytics, Post.id == PostAnalytics.post_id)\
            .outerjoin(ViewSession, Post.id == ViewSession.post_id)\
            .outerjoin(LinkClick, Post.id == LinkClick.post_id)\
            .group_by(Post.id, PostAnalytics.views, PostAnalytics.likes, PostAnalytics.shares).all()

        link_clicks = db.session.query(
            Post.title,
            LinkClick.clicked_url,
            LinkClick.link_text,
            func.count(LinkClick.id).label("clicks"),
            func.count(func.distinct(LinkClick.device_id)).label("unique_users"),
            func.max(LinkClick.created_at).label("last_clicked")
        ).join(Post, Post.id == LinkClick.post_id)\
            .group_by(Post.title, LinkClick.clicked_url, LinkClick.link_text)\
            .order_by(func.count(LinkClick.id).desc())\
            .limit(100).all()

        return render_template("admin_analytics.html", data=data, link_clicks=link_clicks)

    # =========================
    # DELETE POST
    # =========================
    @app.post("/admin/delete/<int:id>")
    @login_required
    def delete_post(id):
        post = Post.query.get_or_404(id)

        db.session.delete(post)
        db.session.commit()

        flash("Post deleted", "success")
        return redirect(url_for("admin_dashboard"))

    @app.post("/chatbot")
    def chatbot():
        data = request.get_json() or {}
        user_message = data.get("message", "")

        reply = blog_chatbot_reply(user_message)

        return jsonify({
            "reply": reply
        })

    @app.post("/summary-feedback")
    def summary_feedback():

        data = request.get_json()

        feedback = SummaryFeedback(
            post_id=data.get("post_id"),
            selected=data.get("selected"),
            summary_a=data.get("summary_a"),
            summary_b=data.get("summary_b"),
            user_prompt=data.get("prompt")
          )

        db.session.add(feedback)
        db.session.commit()

        return jsonify({
        "status": "success"
       })

    return app


# =========================
# UTILITIES
# =========================

def send_link_click_email(app, post, clicked_url, link_text, device_id, total_clicks, unique_users, post_clicks):
    if not app.config.get("LINK_CLICK_EMAIL_ENABLED"):
        return

    recipient = app.config.get("LINK_CLICK_ALERT_EMAIL")
    sender = app.config.get("MAIL_DEFAULT_SENDER")
    username = app.config.get("MAIL_USERNAME")
    password = app.config.get("MAIL_PASSWORD")

    if not recipient or not sender or not username or not password:
        app.logger.warning("Link click email skipped: MAIL_USERNAME/MAIL_PASSWORD/LINK_CLICK_ALERT_EMAIL missing.")
        return

    subject = f"StatsDash link clicked: {post.title}"
    body = f"""A user clicked a link on your blog.

Post: {post.title}
Post slug: {post.slug}
Clicked link: {clicked_url}
Link text: {link_text or 'N/A'}
Device/User ID: {device_id or 'N/A'}

Clicks for this link in this post: {post_clicks}
Total clicks for this link: {total_clicks}
Unique users/devices for this link: {unique_users}

Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
"""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body)

    try:
        with smtplib.SMTP(app.config.get("MAIL_SERVER"), app.config.get("MAIL_PORT")) as server:
            if app.config.get("MAIL_USE_TLS"):
                server.starttls()
            server.login(username, password)
            server.send_message(msg)
    except Exception as exc:
        app.logger.exception("Failed to send link click email: %s", exc)

def wrap_lists(html):
    lines = html.split("\n")
    result = []
    in_list = False

    for line in lines:
        if "<li>" in line:
            if not in_list:
                result.append("<ul>")
                in_list = True
            result.append(line)
        else:
            if in_list:
                result.append("</ul>")
                in_list = False
            result.append(line)

    if in_list:
        result.append("</ul>")

    return "\n".join(result)
def extract_rich_content(file):
    name = file.filename.lower()

    html = ""

    # ================= DOCX =================
    if name.endswith(".docx"):
        doc = Document(file)

        # ---- TEXT ----
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # Detect bullet points
            if para.style.name.lower().startswith("list"):
                html += f"<li>{text}</li>"
            else:
                html += f"<p>{text}</p>"

        # ---- IMAGES ----
        for rel in doc.part._rels:
            rel = doc.part._rels[rel]
            if "image" in rel.target_ref:
                image_data = rel.target_part.blob

                # Upload to Cloudinary
                res = cloudinary.uploader.upload(
                    image_data,
                    folder="statsdash/content_images",
                    resource_type="image"
                )

                img_url = res["secure_url"]

                html += f'<img src="{img_url}" class="media">'

        return html

    # ================= RTF =================
    elif name.endswith(".rtf"):
        text = rtf_to_text(file.read().decode())
        return "".join(f"<p>{line}</p>" for line in text.split("\n") if line.strip())

    # ================= TXT =================
    elif name.endswith(".txt"):
        text = file.read().decode()
        return "".join(f"<p>{line}</p>" for line in text.split("\n") if line.strip())

    return ""

def manage_db_size():
    total = db.session.query(func.sum(func.length(Post.content))).scalar() or 0
    mb = total / (1024 * 1024)

    if mb > MAX_DB_MB:
        oldest = Post.query.order_by(Post.created_at.asc()).first()
        if oldest:
            db.session.delete(oldest)
            db.session.commit()


def slugify(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def make_unique_slug(title):
    base = slugify(title)
    slug = base
    i = 1

    while Post.query.filter_by(slug=slug).first():
        i += 1
        slug = f"{base}-{i}"

    return slug


def ensure_default_admin():
    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD", "admin123")

    user = User.query.filter_by(username=username).first()

    if not user:
        db.session.add(User(
            username=username,
            password_hash=generate_password_hash(password),
            is_admin=True
        ))
        db.session.commit()


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
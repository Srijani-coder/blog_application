import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, send_from_directory, abort, jsonify
)
from flask_login import (
    LoginManager, login_user, login_required, logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from config import Config
from models import db, User, Post, Comment


COMMENTS_PAGE_SIZE = 10


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Ensure folders exist
    Path("instance").mkdir(exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(exist_ok=True)
    Path(os.path.join(app.config["UPLOAD_FOLDER"], "images")).mkdir(exist_ok=True)
    Path(os.path.join(app.config["UPLOAD_FOLDER"], "videos")).mkdir(exist_ok=True)

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = "admin_login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    with app.app_context():
        db.create_all()
        ensure_default_admin(app)

    # ---------------------------
    # Public routes
    # ---------------------------
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
            .order_by(Post.publish_date.desc(), Post.created_at.desc())
            .all()
        )

        # For today's post: initial comments + count for "read more"
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

    @app.get("/post/<slug>")
    def post_detail(slug: str):
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

    # Create a comment (public)
    @app.post("/post/<slug>/comment")
    def add_comment(slug: str):
        post = Post.query.filter_by(slug=slug).first_or_404()

        name = (request.form.get("name") or "").strip()
        text = (request.form.get("text") or "").strip()

        if not name or not text:
            flash("Please enter your name and a comment.", "error")
            # Return to same page (home uses anchor, post uses same slug page)
            ref = request.referrer or url_for("post_detail", slug=slug)
            return redirect(ref)

        # light spam guard
        if len(name) > 80 or len(text) > 4000:
            flash("Comment too long.", "error")
            ref = request.referrer or url_for("post_detail", slug=slug)
            return redirect(ref)

        db.session.add(Comment(post_id=post.id, name=name, text=text))
        db.session.commit()

        flash("Comment posted!", "success")
        ref = request.referrer or url_for("post_detail", slug=slug)
        return redirect(ref)

    # Load comments in batches (AJAX)
    @app.get("/post/<slug>/comments")
    def get_comments(slug: str):
        post = Post.query.filter_by(slug=slug).first_or_404()

        try:
            offset = int(request.args.get("offset", "0"))
        except ValueError:
            offset = 0

        limit = COMMENTS_PAGE_SIZE

        total = post.comments.count()
        rows = (
            post.comments
            .order_by(Comment.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        data = [{
            "id": c.id,
            "name": c.name,
            "text": c.text,
            "created_at": c.created_at.strftime("%Y-%m-%d %H:%M UTC")
        } for c in rows]

        has_more = (offset + len(rows)) < total

        return jsonify({
            "comments": data,
            "next_offset": offset + len(rows),
            "has_more": has_more,
            "total": total
        })

    # Serve uploaded files
    @app.get("/uploads/<path:filepath>")
    def uploaded_file(filepath: str):
        safe_root = os.path.abspath(app.config["UPLOAD_FOLDER"])
        requested = os.path.abspath(os.path.join(safe_root, filepath))
        if not requested.startswith(safe_root):
            abort(403)
        return send_from_directory(safe_root, filepath)

    # ---------------------------
    # Admin routes (separate URL)
    # ---------------------------
    @app.get("/admin/login")
    def admin_login():
        if current_user.is_authenticated:
            return redirect(url_for("admin_posts"))
        return render_template("admin_login.html")

    @app.post("/admin/login")
    def admin_login_post():
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid credentials.", "error")
            return redirect(url_for("admin_login"))

        login_user(user)
        return redirect(url_for("admin_posts"))

    @app.get("/admin/logout")
    @login_required
    def admin_logout():
        logout_user()
        return redirect(url_for("home"))

    @app.get("/admin")
    @login_required
    def admin_posts():
        posts = Post.query.order_by(Post.publish_date.desc(), Post.created_at.desc()).all()
        return render_template("admin_posts.html", posts=posts)

    @app.get("/admin/new")
    @login_required
    def admin_new_post():
        return render_template("admin_new_post.html")

    @app.post("/admin/new")
    @login_required
    def admin_new_post_post():
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()

        if not title or not content:
            flash("Title and content are required.", "error")
            return redirect(url_for("admin_new_post"))

        latest = Post.query.order_by(Post.publish_date.desc(), Post.created_at.desc()).first()
        if latest:
            delta = (date.today() - latest.publish_date).days
            if delta < 7:
                flash(f"Posting is locked. Next post allowed in {7 - delta} day(s).", "error")
                return redirect(url_for("admin_new_post"))

        slug = make_unique_slug(title)

        image_file = request.files.get("image")
        video_file = request.files.get("video")

        image_path = None
        video_path = None

        try:
            if image_file and image_file.filename:
                image_path = save_upload(app, image_file, kind="image")

            if video_file and video_file.filename:
                video_path = save_upload(app, video_file, kind="video")
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin_new_post"))

        post = Post(
            title=title,
            slug=slug,
            content=content,
            image_path=image_path,
            video_path=video_path,
            publish_date=date.today()
        )

        db.session.add(post)
        db.session.commit()

        flash("Post published!", "success")
        return redirect(url_for("admin_posts"))

    return app


# ---------------------------
# Helpers
# ---------------------------
def ensure_default_admin(app: Flask):
    default_user = os.environ.get("ADMIN_USERNAME", "admin")
    default_pass = os.environ.get("ADMIN_PASSWORD", "admin123")

    existing = User.query.filter_by(username=default_user).first()
    if not existing:
        u = User(
            username=default_user,
            password_hash=generate_password_hash(default_pass),
            is_admin=True
        )
        db.session.add(u)
        db.session.commit()
        app.logger.warning("Default admin created. CHANGE ADMIN_PASSWORD in production.")


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    return text.strip("-") or "post"


def make_unique_slug(title: str) -> str:
    base = slugify(title)
    slug = base
    i = 2
    while Post.query.filter_by(slug=slug).first() is not None:
        slug = f"{base}-{i}"
        i += 1
    return slug


def allowed_ext(app: Flask, filename: str, kind: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if kind == "image":
        return ext in app.config["ALLOWED_IMAGE_EXT"]
    if kind == "video":
        return ext in app.config["ALLOWED_VIDEO_EXT"]
    return False


def save_upload(app: Flask, file_storage, kind: str) -> str:
    filename = secure_filename(file_storage.filename)
    if not filename:
        raise ValueError("Invalid filename")

    if not allowed_ext(app, filename, kind):
        raise ValueError(f"File type not allowed for {kind}: {filename}")

    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    final_name = f"{stamp}_{filename}"

    subdir = "images" if kind == "image" else "videos"
    save_dir = os.path.join(app.config["UPLOAD_FOLDER"], subdir)
    os.makedirs(save_dir, exist_ok=True)

    abs_path = os.path.join(save_dir, final_name)
    file_storage.save(abs_path)

    return f"{subdir}/{final_name}"


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)

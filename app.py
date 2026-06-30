import os
import re
import smtplib
import secrets
import json
from urllib.parse import urljoin
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, datetime, timedelta
from dotenv import load_dotenv
from models import SummaryFeedback

load_dotenv()

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_file, Response, abort
)
from flask_login import (
    LoginManager, login_user, login_required, logout_user
)
from werkzeug.security import generate_password_hash, check_password_hash

from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, text, inspect
from xml.sax.saxutils import escape as xml_escape

import cloudinary
import cloudinary.uploader

from docx_rich_importer import extract_rich_content

from config import Config
from models import db, User, Post, Comment, PostAnalytics, ViewSession, ShareEvent, Subscriber, NewsletterLog
from chatbot import blog_chatbot_reply


COMMENTS_PAGE_SIZE = 10
MAX_DB_MB = 1000  # 1GB


# ✅ CLOUDINARY (uses CLOUDINARY_URL automatically)
cloudinary.config(secure=True)


# =========================
# SEO HELPERS
# =========================
SITE_NAME = "JuicyStatControversy"
SITE_DESCRIPTION = (
    "Data stories, statistics, AI analysis, social issues, finance investigations, "
)
BASE_SEO_KEYWORDS = [
    "data analysis blog",
    "statistics blog",
    "current statistics",
    "data storytelling",
    "AI applications",
    "visual dashboards",
    "crime data analysis",
    "finance investigation",
    "bullying prevention",
    "social issue analysis",
    "India statistics",
    "research based articles",
    "public data analysis",
]
KEYWORD_BANK = [
    "rape statistics", "violence against women", "forced marriage", "victim blaming",
    "financial fraud", "chit fund", "Indian finance", "government data",
    "bullying", "cyberbullying", "anti bullying AI", "student safety",
    "plagiarism detection", "concept similarity", "copyright risk", "AI research",
    "quantum computing", "fraud detection", "machine learning", "forecasting",
    "dashboard", "Tableau", "Power BI", "Python data visualization",
]

def clean_text_from_html(html):
    """Convert stored article HTML into readable plain text for SEO snippets."""
    text = re.sub(r"<script[\s\S]*?</script>", " ", html or "", flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def seo_description(post=None, limit=160):
    if not post:
        return SITE_DESCRIPTION[:limit]
    text = clean_text_from_html(post.content)
    source = text or post.title or SITE_DESCRIPTION
    return source[:limit].rsplit(" ", 1)[0]


def seo_keywords(post=None):
    """Build contextual keyword phrases from title/content plus a curated bank.

    Note: Google does not use sitemap keyword tags, but strong titles,
    descriptions, schema keywords, and page content help Google understand context.
    """
    words = list(BASE_SEO_KEYWORDS)
    if post:
        combined = f"{post.title} {clean_text_from_html(post.content)[:1200]}".lower()
        for keyword in KEYWORD_BANK:
            if any(part in combined for part in keyword.lower().split()[:2]):
                words.append(keyword)
        title_terms = [w for w in re.findall(r"[a-zA-Z][a-zA-Z]{3,}", post.title.lower()) if w not in {"with", "from", "that", "this"}]
        words.extend(title_terms[:8])
    # de-duplicate while preserving order
    seen = set()
    result = []
    for item in words:
        item = item.strip()
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            result.append(item)
    return result[:28]




def get_site_url():
    """Return the canonical public site URL. Set SITE_URL=https://yourdomain.com in Render."""
    return (os.environ.get("SITE_URL") or os.environ.get("PUBLIC_SITE_URL") or "").rstrip("/")


def external_url(endpoint, **values):
    """Build absolute URLs using SITE_URL when configured; otherwise use Flask host."""
    public_site = get_site_url()
    relative = url_for(endpoint, **values)
    if public_site:
        return urljoin(public_site + "/", relative.lstrip("/"))
    return url_for(endpoint, _external=True, **values)


def canonical_for_current_request():
    """Canonical without tracking/query parameters."""
    public_site = get_site_url()
    path = request.path.rstrip("/") or "/"
    if public_site:
        return public_site + path
    return request.url_root.rstrip("/") + path


def seo_image(post=None):
    if post and post.image_path:
        return post.image_path
    public_site = get_site_url()
    if public_site:
        return public_site + url_for("static", filename="profile.jpg")
    return url_for("static", filename="profile.jpg", _external=True)


def reading_time_minutes(html):
    words = clean_text_from_html(html).split()
    return max(1, round(len(words) / 220))


def build_article_schema(post):
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": post.title[:110],
        "description": seo_description(post),
        "image": [seo_image(post)],
        "author": {"@type": "Person", "name": "Srijani Chakrabarti"},
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "logo": {"@type": "ImageObject", "url": seo_image(None)}
        },
        "mainEntityOfPage": {"@type": "WebPage", "@id": external_url("post_detail", slug=post.slug)},
        "datePublished": post.publish_date.isoformat() if post.publish_date else None,
        "dateModified": post.created_at.date().isoformat() if post.created_at else None,
        "keywords": seo_keywords(post),
        "wordCount": len(clean_text_from_html(post.content).split())
    }


def build_website_schema():
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "description": SITE_DESCRIPTION,
        "url": get_site_url() or request.url_root.rstrip("/"),
        "publisher": {"@type": "Person", "name": "Srijani Chakrabarti"}
    }

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

    @app.context_processor
    def inject_global_template_vars():
        active_subscribers = Subscriber.query.filter_by(is_active=True).count()
        return {
            "active_subscribers_count": active_subscribers,
            "site_name": SITE_NAME,
            "default_meta_description": SITE_DESCRIPTION,
            "default_meta_keywords": ", ".join(BASE_SEO_KEYWORDS),
            "canonical_url": canonical_for_current_request(),
            "default_og_image": seo_image(None),
            "website_schema": build_website_schema(),
        }

    @app.template_filter("plain")
    def plain_filter(value):
        return clean_text_from_html(value)

    @app.template_filter("reading_time")
    def reading_time_filter(value):
        return reading_time_minutes(value)

    @app.after_request
    def add_seo_and_security_headers(response):
        # Keep private/admin URLs out of search results even if linked accidentally.
        if request.path.startswith("/admin") or request.path.startswith("/unsubscribe"):
            response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        return response

    with app.app_context():
        db.create_all()
        ensure_tracking_schema()
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
            comments_page_size=COMMENTS_PAGE_SIZE,
            meta_description=SITE_DESCRIPTION,
            meta_keywords=", ".join(BASE_SEO_KEYWORDS),
            canonical_url=external_url("home"),
            og_image=seo_image(todays_post),
        )

    # =========================
    # POSTS
    # =========================
    @app.get("/posts")
    def posts():
        posts = Post.query.order_by(Post.publish_date.desc()).all()
        return render_template(
            "posts.html",
            posts=posts,
            meta_description="Browse all JuicyStatControversy data stories, statistics articles, dashboards, social analysis, finance investigations, and AI research posts.",
            meta_keywords=", ".join(BASE_SEO_KEYWORDS + ["all blog posts", "latest statistics articles"]),
            canonical_url=external_url("posts"),
            og_image=seo_image(posts[0] if posts else None),
        )

    # =========================
    # SEO: SITEMAP + ROBOTS
    # =========================
    @app.get("/sitemap.xml")
    def sitemap_xml():
        """Dynamic XML sitemap for Google Search Console."""
        posts = Post.query.order_by(Post.publish_date.desc()).all()
        today_iso = date.today().isoformat()

        urls = [
            {
                "loc": external_url("home"),
                "lastmod": today_iso,
                "changefreq": "daily",
                "priority": "1.0",
            },
            {
                "loc": external_url("posts"),
                "lastmod": today_iso,
                "changefreq": "daily",
                "priority": "0.9",
            },
        ]

        for post in posts:
            lastmod = (post.created_at.date() if post.created_at else post.publish_date).isoformat()
            item = {
                "loc": external_url("post_detail", slug=post.slug),
                "lastmod": lastmod,
                "changefreq": "weekly",
                "priority": "0.8",
            }
            if post.image_path:
                item["image"] = post.image_path
                item["image_title"] = post.title
            urls.append(item)

        xml_urls = []
        for item in urls:
            image_xml = ""
            if item.get("image"):
                image_xml = f"""
        <image:image>
            <image:loc>{xml_escape(item['image'])}</image:loc>
            <image:title>{xml_escape(item.get('image_title', ''))}</image:title>
        </image:image>"""
            xml_urls.append(f"""
    <url>
        <loc>{xml_escape(item['loc'])}</loc>
        <lastmod>{item['lastmod']}</lastmod>
        <changefreq>{item['changefreq']}</changefreq>
        <priority>{item['priority']}</priority>{image_xml}
    </url>""")

        xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
%s
</urlset>
""" % "".join(xml_urls)
        return Response(xml, mimetype="application/xml")

    @app.get("/robots.txt")
    def robots_txt():
        robots = f"""User-agent: *
Allow: /
Disallow: /admin
Disallow: /admin/
Disallow: /unsubscribe/

Sitemap: {external_url('sitemap_xml')}
"""
        return Response(robots, mimetype="text/plain")

    @app.get("/feed.xml")
    def feed_xml():
        posts = Post.query.order_by(Post.publish_date.desc(), Post.created_at.desc()).limit(30).all()
        items = []
        for post in posts:
            pub_dt = datetime.combine(post.publish_date, datetime.min.time()) if post.publish_date else post.created_at
            pub_rfc = pub_dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
            post_url = external_url("post_detail", slug=post.slug)
            items.append(f"""
        <item>
            <title>{xml_escape(post.title)}</title>
            <link>{xml_escape(post_url)}</link>
            <guid>{xml_escape(post_url)}</guid>
            <pubDate>{pub_rfc}</pubDate>
            <description>{xml_escape(seo_description(post, 300))}</description>
        </item>""")
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>{xml_escape(SITE_NAME)}</title>
        <link>{xml_escape(external_url("home"))}</link>
        <description>{xml_escape(SITE_DESCRIPTION)}</description>
        {''.join(items)}
    </channel>
</rss>
"""
        return Response(xml, mimetype="application/rss+xml")

    @app.get("/llms.txt")
    def llms_txt():
        recent = Post.query.order_by(Post.publish_date.desc(), Post.created_at.desc()).limit(20).all()
        lines = [
            f"# {SITE_NAME}",
            SITE_DESCRIPTION,
            "",
            "## Important pages",
            f"- Home: {external_url('home')}",
            f"- All posts: {external_url('posts')}",
            f"- Sitemap: {external_url('sitemap_xml')}",
            f"- RSS feed: {external_url('feed_xml')}",
            "",
            "## Recent articles",
        ]
        for post in recent:
            lines.append(f"- {post.title}: {external_url('post_detail', slug=post.slug)}")
        return Response("\n".join(lines) + "\n", mimetype="text/plain")

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

        analytics = PostAnalytics.query.filter_by(post_id=post.id).first()
        if not analytics:
            analytics = PostAnalytics(post_id=post.id)
            db.session.add(analytics)
            db.session.commit()

        return render_template(
            "post.html",
            post=post,
            analytics=analytics,
            initial_comments=initial_comments,
            comment_count=comment_count,
            comments_page_size=COMMENTS_PAGE_SIZE,
            meta_description=seo_description(post),
            meta_keywords=", ".join(seo_keywords(post)),
            post_keywords=seo_keywords(post),
            canonical_url=external_url("post_detail", slug=post.slug),
            og_image=seo_image(post),
            article_schema=build_article_schema(post),
            reading_minutes=reading_time_minutes(post.content),
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
    # NEWSLETTER SUBSCRIPTION
    # =========================
    @app.post("/subscribe")
    def subscribe():
        email = (request.form.get("email") or "").strip().lower()
        name = (request.form.get("name") or "").strip()[:120]

        if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            flash("Please enter a valid email address.", "error")
            return redirect(request.referrer or url_for("home"))

        subscriber = Subscriber.query.filter_by(email=email).first()
        if subscriber:
            subscriber.name = name or subscriber.name
            subscriber.is_active = True
            subscriber.unsubscribed_at = None
            flash("You are subscribed to the StatDash newsletter.", "success")
        else:
            db.session.add(Subscriber(email=email, name=name or None, source="website"))
            flash("Subscription successful! You will receive new article updates.", "success")

        db.session.commit()
        return redirect(request.referrer or url_for("home"))

    @app.get("/unsubscribe/<int:subscriber_id>/<token>")
    def unsubscribe(subscriber_id, token):
        subscriber = db.session.get(Subscriber, subscriber_id)
        if not subscriber or token != make_unsubscribe_token(subscriber):
            flash("Invalid unsubscribe link.", "error")
            return redirect(url_for("home"))

        subscriber.is_active = False
        subscriber.unsubscribed_at = datetime.utcnow()
        db.session.commit()
        flash("You have been unsubscribed from the newsletter.", "success")
        return redirect(url_for("home"))

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
        subscriber_count = Subscriber.query.filter_by(is_active=True).count()
        return render_template("admin_posts.html", posts=posts, subscriber_count=subscriber_count)

    # =========================
    # CREATE POST (🔥 UPGRADED)
    # =========================
    @app.route("/admin/new", methods=["GET", "POST"])
    @login_required
    def new_post():
        if request.method == "POST":

            title = request.form["title"]
            content = request.form.get("content", "")

            # DOC upload: preserve Word formatting, inline images, hyperlinks, tables and spacing.
            # Admin can enter one image alt text per line; these are assigned to DOCX images in order.
            docfile = request.files.get("docfile")
            docx_image_alt_texts = [
                line.strip()
                for line in request.form.get("docx_image_alt_texts", "").splitlines()
                if line.strip()
            ]
            if docfile and docfile.filename:
                content = extract_rich_content(docfile, image_alt_texts=docx_image_alt_texts)

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
    # ANALYTICS / TRACKING
    # =========================
    def get_or_create_analytics(post_id):
        analytics = PostAnalytics.query.filter_by(post_id=post_id).first()
        if not analytics:
            analytics = PostAnalytics(post_id=post_id)
            db.session.add(analytics)
            db.session.flush()
        return analytics

    def request_json():
        return request.get_json(silent=True) or {}

    @app.post("/track/view/<slug>")
    def track_view(slug):
        post = Post.query.filter_by(slug=slug).first_or_404()
        data = request_json()
        device_id = (data.get("device_id") or request.remote_addr or "unknown")[:120]

        analytics = get_or_create_analytics(post.id)

        # Count one view per device per calendar day, but still create a session
        # every time the user opens the post so reading time can be averaged.
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        existing_today = ViewSession.query.filter(
            ViewSession.post_id == post.id,
            ViewSession.device_id == device_id,
            ViewSession.started_at >= today_start
        ).first()

        if not existing_today:
            analytics.views += 1

        session = ViewSession(post_id=post.id, device_id=device_id, duration=0)
        db.session.add(session)
        db.session.commit()

        return jsonify({
            "session_id": session.id,
            "views": analytics.views,
            "likes": analytics.likes,
            "shares": analytics.shares
        })

    @app.post("/track/time")
    def track_time():
        data = request_json()
        session_id = data.get("session_id")
        duration = data.get("duration", 0)

        try:
            duration = max(0, min(float(duration), 24 * 60 * 60))
        except (TypeError, ValueError):
            duration = 0

        session = db.session.get(ViewSession, session_id) if session_id else None
        if session:
            # Keep the largest duration sent for this session, because the browser
            # may send updates several times before leaving the page.
            session.duration = max(session.duration or 0, duration)
            db.session.commit()

        return jsonify({"status": "ok"})

    @app.post("/track/like/<slug>")
    def like_post(slug):
        post = Post.query.filter_by(slug=slug).first_or_404()
        data = request_json()
        device_id = (data.get("device_id") or request.remote_addr or "unknown")[:120]

        analytics = get_or_create_analytics(post.id)

        existing = ShareEvent.query.filter_by(
            post_id=post.id,
            platform="like",
            device_id=device_id
        ).first()

        liked = False
        if not existing:
            analytics.likes += 1
            liked = True
            db.session.add(ShareEvent(
                post_id=post.id,
                platform="like",
                device_id=device_id
            ))

        db.session.commit()
        return jsonify({"likes": analytics.likes, "liked": liked})

    @app.get("/track/stats/<slug>")
    def post_stats(slug):
        post = Post.query.filter_by(slug=slug).first_or_404()
        analytics = get_or_create_analytics(post.id)

        avg_time = db.session.query(func.avg(ViewSession.duration)).filter(
            ViewSession.post_id == post.id,
            ViewSession.duration.isnot(None),
            ViewSession.duration > 0
        ).scalar() or 0

        unique_readers = db.session.query(func.count(func.distinct(ViewSession.device_id))).filter(
            ViewSession.post_id == post.id
        ).scalar() or 0

        db.session.commit()
        return jsonify({
            "views": analytics.views,
            "likes": analytics.likes,
            "shares": analytics.shares,
            "avg_time_seconds": round(float(avg_time), 1),
            "unique_readers": unique_readers
        })

    @app.post("/track/share/<slug>")
    def share_post(slug):
        post = Post.query.filter_by(slug=slug).first_or_404()
        data = request_json()
        platform = (data.get("platform") or "unknown")[:50]
        device_id = (data.get("device_id") or request.remote_addr or "unknown")[:120]

        analytics = get_or_create_analytics(post.id)
        analytics.shares += 1

        db.session.add(ShareEvent(
            post_id=post.id,
            platform=platform,
            device_id=device_id
        ))
        db.session.commit()

        return jsonify({"shares": analytics.shares})

    # =========================
    # NEWSLETTER ADMIN
    # =========================
    @app.get("/admin/subscribers")
    @login_required
    def admin_subscribers():
        subscribers = Subscriber.query.order_by(Subscriber.subscribed_at.desc()).all()
        logs = NewsletterLog.query.order_by(NewsletterLog.sent_at.desc()).limit(50).all()
        return render_template("admin_subscribers.html", subscribers=subscribers, logs=logs)

    @app.post("/admin/notify/<int:id>")
    @login_required
    def notify_subscribers(id):
        post = Post.query.get_or_404(id)
        subscribers = Subscriber.query.filter_by(is_active=True).order_by(Subscriber.subscribed_at.desc()).all()

        if not subscribers:
            flash("No active subscribers found.", "error")
            return redirect(url_for("admin_dashboard"))

        sent = 0
        failed = 0

        for subscriber in subscribers:
            try:
                send_newsletter_email(app, post, subscriber)
                subscriber.last_notified_at = datetime.utcnow()
                db.session.add(NewsletterLog(
                    post_id=post.id,
                    subscriber_id=subscriber.id,
                    email=subscriber.email,
                    status="sent"
                ))
                sent += 1
            except Exception as exc:
                failed += 1
                db.session.add(NewsletterLog(
                    post_id=post.id,
                    subscriber_id=subscriber.id,
                    email=subscriber.email,
                    status="failed",
                    error_message=str(exc)[:2000]
                ))

        db.session.commit()
        flash(f"Newsletter finished: {sent} sent, {failed} failed.", "success" if sent else "error")
        return redirect(url_for("admin_subscribers"))

    # =========================
    # ANALYTICS DASHBOARD
    # =========================
    @app.get("/admin/analytics")
    @login_required
    def analytics_dashboard():
        posts = Post.query.order_by(Post.publish_date.desc()).all()
        data = []

        for post in posts:
            analytics = PostAnalytics.query.filter_by(post_id=post.id).first()
            avg_time = db.session.query(func.avg(ViewSession.duration)).filter(
                ViewSession.post_id == post.id,
                ViewSession.duration.isnot(None),
                ViewSession.duration > 0
            ).scalar() or 0
            unique_readers = db.session.query(func.count(func.distinct(ViewSession.device_id))).filter(
                ViewSession.post_id == post.id
            ).scalar() or 0

            data.append((
                post.title,
                analytics.views if analytics else 0,
                analytics.likes if analytics else 0,
                analytics.shares if analytics else 0,
                float(avg_time),
                unique_readers
            ))

        return render_template("admin_analytics.html", data=data)

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

def wrap_lists(html):
    """Wrap plain <li> lines from manually typed content.

    Rich DOCX imports already include proper <ul>/<ol> containers, so leave those
    untouched to avoid nested or broken lists.
    """
    if not html:
        return html
    if "<ul" in html.lower() or "<ol" in html.lower():
        return html

    lines = html.split("\n")
    result = []
    in_list = False

    for line in lines:
        if "<li" in line.lower():
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

def post_plain_summary(html, limit=420):
    """Create a clean email preview from stored post HTML."""
    try:
        from bs4 import BeautifulSoup
        text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html or "")
        text = re.sub(r"\s+", " ", text).strip()

    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


def make_unsubscribe_token(subscriber):
    import hashlib
    raw = f"{subscriber.id}:{subscriber.email}:{current_secret()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def current_secret():
    return os.environ.get("SECRET_KEY") or "dev-secret-key"


def render_newsletter_html(app, post, subscriber):
    post_url = external_url("post_detail", slug=post.slug)
    unsubscribe_url = url_for(
        "unsubscribe",
        subscriber_id=subscriber.id,
        token=make_unsubscribe_token(subscriber),
        _external=True
    )
    summary = post_plain_summary(post.content)
    image_block = ""
    if post.image_path:
        image_block = f"""
        <img src=\"{post.image_path}\" alt=\"{post.title}\" style=\"width:100%;max-height:360px;object-fit:cover;border-radius:18px;margin:18px 0;border:1px solid #e9d5ff;\">
        """

    greeting = f"Hi {subscriber.name}," if subscriber.name else "Hi reader,"

    return f"""
    <!doctype html>
    <html>
    <body style=\"margin:0;background:#0f1020;font-family:Arial,Helvetica,sans-serif;color:#1f2937;\">
      <div style=\"padding:28px 12px;background:linear-gradient(135deg,#31115f,#7c3aed,#ec4899);\">
        <div style=\"max-width:680px;margin:auto;background:#ffffff;border-radius:24px;overflow:hidden;box-shadow:0 18px 50px rgba(0,0,0,.25);\">
          <div style=\"padding:26px 28px;background:linear-gradient(135deg,#1e1b4b,#6d28d9);color:white;\">
            <div style=\"font-size:13px;letter-spacing:.12em;text-transform:uppercase;opacity:.85;\">New StatDash Article</div>
            <h1 style=\"margin:10px 0 6px;font-size:30px;line-height:1.18;\">{post.title}</h1>
            <div style=\"font-size:14px;opacity:.9;\">Published {post.publish_date}</div>
          </div>

          <div style=\"padding:28px;\">
            <p style=\"font-size:16px;line-height:1.7;margin:0 0 12px;\">{greeting}</p>
            <p style=\"font-size:17px;line-height:1.75;margin:0 0 14px;\">A new data story is live on <b>JuicyStatControversy / StatDash</b>.</p>
            {image_block}
            <div style=\"background:#f5f3ff;border:1px solid #ddd6fe;border-radius:18px;padding:18px 20px;margin:18px 0;\">
              <div style=\"font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:#6d28d9;font-weight:bold;margin-bottom:8px;\">Quick Summary</div>
              <p style=\"font-size:16px;line-height:1.75;margin:0;color:#374151;\">{summary}</p>
            </div>

            <a href=\"{post_url}\" style=\"display:inline-block;background:linear-gradient(135deg,#7c3aed,#ec4899);color:white;text-decoration:none;font-weight:bold;padding:14px 22px;border-radius:999px;margin:10px 0 20px;\">Read the full article →</a>

            <p style=\"font-size:13px;line-height:1.6;color:#6b7280;margin-top:22px;\">You received this because you subscribed to StatDash updates. <a href=\"{unsubscribe_url}\" style=\"color:#7c3aed;\">Unsubscribe</a></p>
          </div>
        </div>
      </div>
    </body>
    </html>
    """


def send_newsletter_email(app, post, subscriber):
    username = app.config.get("MAIL_USERNAME")
    password = app.config.get("MAIL_PASSWORD")
    sender = app.config.get("MAIL_DEFAULT_SENDER")

    if not username or not password:
        raise RuntimeError("MAIL_USERNAME and MAIL_PASSWORD are not configured in environment variables.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"New StatDash article: {post.title}"
    msg["From"] = sender
    msg["To"] = subscriber.email

    post_url = external_url("post_detail", slug=post.slug)
    text_body = f"New StatDash article: {post.title}\n\n{post_plain_summary(post.content)}\n\nRead: {post_url}"
    html_body = render_newsletter_html(app, post, subscriber)

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(app.config.get("MAIL_SERVER"), app.config.get("MAIL_PORT")) as server:
        if app.config.get("MAIL_USE_TLS"):
            server.starttls()
        server.login(username, password)
        server.sendmail(sender, [subscriber.email], msg.as_string())

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



def ensure_tracking_schema():
    """Add missing tracking columns for existing deployed databases.

    db.create_all() creates new tables but does not alter old tables.
    This keeps older Render/Postgres or local SQLite databases compatible
    with the new per-device reading-time and like tracking code.
    """
    inspector = inspect(db.engine)

    if "view_sessions" in inspector.get_table_names():
        cols = {col["name"] for col in inspector.get_columns("view_sessions")}
        dialect = db.engine.dialect.name

        if "device_id" not in cols:
            db.session.execute(text("ALTER TABLE view_sessions ADD COLUMN device_id VARCHAR(120)"))

        if "duration" not in cols:
            col_type = "DOUBLE PRECISION" if dialect == "postgresql" else "FLOAT"
            db.session.execute(text(f"ALTER TABLE view_sessions ADD COLUMN duration {col_type}"))

        db.session.commit()

    if "post_analytics" in inspector.get_table_names():
        cols = {col["name"] for col in inspector.get_columns("post_analytics")}
        for col in ("views", "likes", "shares"):
            if col not in cols:
                db.session.execute(text(f"ALTER TABLE post_analytics ADD COLUMN {col} INTEGER DEFAULT 0 NOT NULL"))
        db.session.commit()

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
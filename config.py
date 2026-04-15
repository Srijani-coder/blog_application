import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # =========================
    # SECURITY
    # =========================
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    # =========================
    # DATABASE (AIVEN READY)
    # =========================
    DATABASE_URL = os.environ.get("DATABASE_URL")

    if DATABASE_URL:
        # Fix old postgres:// issue (Aiven / Heroku)
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

        SQLALCHEMY_DATABASE_URI = DATABASE_URL
    else:
        # Fallback to SQLite (local development)
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "instance", "blog.db")

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Better connection stability (important for cloud DB like Aiven)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # =========================
    # FILE STORAGE
    # =========================
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 800 * 1024 * 1024  # 800MB

    # Ensure required folders exist
    os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # =========================
    # FILE VALIDATION
    # =========================
    ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
    ALLOWED_VIDEO_EXT = {"mp4", "webm", "mov", "m4v"}

    # =========================
    # CLOUDINARY (OPTIONAL)
    # =========================
    CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET")

    # =========================
    # APP SETTINGS
    # =========================
    POSTS_PER_PAGE = 10
    COMMENTS_PAGE_SIZE = 10
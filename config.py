import os
import tempfile

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    """Негізгі баптаулар. Құпия мәндер .env файлынан оқылады."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    # Flask-SQLAlchemy салыстырмалы SQLite жолын instance/ қалтасына қатысты есептейді
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///weather.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "app", "static", "uploads")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", 5)) * 1024 * 1024

    STATIONS_PER_PAGE = 6
    OBSERVATIONS_PER_PAGE = 15
    USERS_PER_PAGE = 10
    API_MAX_PER_PAGE = 100


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    UPLOAD_FOLDER = tempfile.mkdtemp(prefix="weather-uploads-")

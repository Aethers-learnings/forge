"""
Forge demo backend
-------------------
Flask + SQLite API backing the Forge front-end, with the compliance
features required by the hackathon brief:

  * institutional-email domain filtering + non-public admin provisioning
    (admin can never be self-registered)
  * alumni verification queue for grads whose student email has lapsed
  * business verification + opportunity approval pipeline (listings stay
    invisible to students until an admin approves them)
  * skill-overlap job matching, not a hardcoded percentage
  * keyword-vocabulary CV skill extraction (drop-in swap for spaCy later)
  * real LLM career coach when ANTHROPIC_API_KEY is set, rule-based fallback
  * WebSocket push (Flask-SocketIO) for messages/likes/comments/matches
  * video upload -> transcode/thumbnail pipeline (ffmpeg when available)
  * three analytics dashboards (student / business / admin)
  * admin user management, announcements, POPIA data export

Serves the API under /api/... and the front-end HTML at / from static/.
"""
import json
import os
import re
import secrets
import shutil
import subprocess
import time
import urllib.request
import urllib.error
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import urlsplit

from click import ClickException
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, abort, jsonify, request, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, join_room
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)


# Keep local development convenient without ever giving a deployed process a
# predictable signing key.  Tests also use this seam to point SQLAlchemy at a
# throw-away SQLite database instead of the project instance database.
INSECURE_SECRET_KEYS = frozenset({
    "dev-secret-change-me",
    "change-me",
    "change-me-to-something-random",
    "secret",
})
DEPLOYMENT_ENVIRONMENTS = frozenset({"production", "prod", "staging"})
VALID_ENVIRONMENTS = DEPLOYMENT_ENVIRONMENTS | frozenset({"development", "test"})
TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_ENV_VALUES = frozenset({"0", "false", "no", "off", ""})


def _env_bool(environ, name, default=False):
    """Parse an explicit boolean environment value without treating typos as true."""
    raw = environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in TRUE_ENV_VALUES:
        return True
    if value in FALSE_ENV_VALUES:
        return False
    raise RuntimeError(
        f"{name} must be one of: 1/0, true/false, yes/no, on/off."
    )


def build_app_config(environ=None):
    """Return Forge's environment-derived Flask configuration.

    A production process must receive an explicit, high-entropy signing
    secret. Local development gets a process-local random secret, which keeps
    the demo usable but never falls back to a value an attacker can know.
    """
    environ = os.environ if environ is None else environ
    environment = environ.get("FORGE_ENV", "development").strip().lower()
    if environment not in VALID_ENVIRONMENTS:
        raise RuntimeError(
            "FORGE_ENV must be one of: development, test, staging, production, prod."
        )
    deployment = environment in DEPLOYMENT_ENVIRONMENTS
    debug = _env_bool(environ, "FORGE_DEBUG", default=False)
    demo_mode = _env_bool(environ, "FORGE_DEMO_MODE", default=False)

    # Debugging and seeded demo identities are local-development conveniences,
    # not deployment modes. Fail closed instead of silently accepting an
    # unsafe environment combination.
    if environment != "development" and debug:
        raise RuntimeError(
            "FORGE_DEBUG may only be enabled when FORGE_ENV=development."
        )
    if environment != "development" and demo_mode:
        raise RuntimeError(
            "FORGE_DEMO_MODE may only be enabled when FORGE_ENV=development."
        )

    secret_key = (environ.get("FORGE_SECRET_KEY") or "").strip()
    invalid_secret = not secret_key or secret_key.lower() in INSECURE_SECRET_KEYS

    if deployment and (invalid_secret or len(secret_key) < 32):
        raise RuntimeError(
            "FORGE_SECRET_KEY must be a non-default value of at least 32 characters "
            "for staging or production deployments."
        )
    if invalid_secret:
        secret_key = secrets.token_urlsafe(48)

    return {
        "SQLALCHEMY_DATABASE_URI": environ.get(
            "FORGE_DATABASE_URI",
            "sqlite:///" + os.path.join(BASE_DIR, "instance", "forge.db"),
        ),
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "SECRET_KEY": secret_key,
        "DEBUG": debug,
        "FORGE_ENVIRONMENT": environment,
        "FORGE_DEMO_MODE": demo_mode,
        "UPLOAD_DIR": environ.get(
            "FORGE_UPLOAD_DIR",
            os.path.join(BASE_DIR, "instance", "uploads"),
        ),
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": deployment,
        "PROFILE_IMAGE_DIR": environ.get(
            "FORGE_PROFILE_IMAGE_DIR",
            os.path.join(BASE_DIR, "instance", "profile_images"),
        ),
    }


app = Flask(__name__, static_folder="static")
app.config.update(build_app_config())

db = SQLAlchemy(app)
# Flask-SocketIO's default origin policy is same-origin. Do not use a wildcard:
# browser sockets carry the authenticated Flask session and receive private
# user/role notifications.
socketio = SocketIO(app, async_mode="threading")

from sqlalchemy import event
from sqlalchemy.engine import Engine


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


ROLES = ("trade", "grad", "business", "admin")
SELF_REGISTER_ROLES = ("trade", "grad", "business")   # admin is never self-registerable
STUDENT_ROLES = ("trade", "grad")
ALLOWED_STUDENT_DOMAINS = (
    "my.richfield.ac.za", "richfield.ac.za",
    "my.aaa.ac.za", "aaa.ac.za",
)

# Video pipeline (brief §2.8). Storage can be isolated in tests/deployments.
UPLOAD_DIR = app.config["UPLOAD_DIR"]
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".m4v", ".avi", ".mkv"}
VIDEO_CONTAINER_FAMILIES = {
    ".mp4": "iso-bmff",
    ".mov": "iso-bmff",
    ".m4v": "iso-bmff",
    ".webm": "ebml",
    ".mkv": "ebml",
    ".avi": "avi",
}
MAX_VIDEO_BYTES = 50 * 1024 * 1024
MAX_VIDEO_REQUEST_BYTES = MAX_VIDEO_BYTES + 512 * 1024

# Werkzeug enforces this while parsing request bodies, before a multipart
# upload can grow without bound in application code. The video route also
# performs its own Content-Length preflight and bounded stream copy.
app.config["MAX_CONTENT_LENGTH"] = MAX_VIDEO_REQUEST_BYTES

# Profile images are isolated from the video/general upload directory.
# Forge decodes and re-encodes them before serving them back to clients.
PROFILE_IMAGE_DIR = app.config["PROFILE_IMAGE_DIR"]
os.makedirs(PROFILE_IMAGE_DIR, exist_ok=True)
MAX_PROFILE_IMAGE_BYTES = 10 * 1024 * 1024
MAX_PROFILE_IMAGE_REQUEST_BYTES = MAX_PROFILE_IMAGE_BYTES + 512 * 1024
MAX_PROFILE_IMAGE_PIXELS = 50_000_000
PROFILE_IMAGE_SIZE = (640, 640)
PROFILE_IMAGE_NAME_RE = re.compile(r"^profile_[0-9a-f]{32}\.jpg$")
PROFILE_IMAGE_MIME_FORMATS = {
    "image/jpeg": "JPEG",
    "image/jpg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}

# First-login walkthrough steps per role (brief §2.6). Frontend
# ONBOARDING_COPY keys match these exactly.
ONBOARDING_STEPS = {
    "trade": ["welcome", "add-photo", "add-skills", "upload-cv", "explore-feed"],
    "grad": ["welcome", "add-photo", "add-skills", "upload-cv", "explore-feed"],
    "business": ["welcome", "company-profile", "post-listing", "explore-candidates"],
    "admin": ["welcome", "review-queue", "explore-dashboard"],
}

SKILL_VOCAB = [
    "MIG welding", "TIG welding", "blueprint reading", "pipe fitting",
    "electrical wiring", "PLC programming", "HVAC installation",
    "pattern cutting", "garment fitting", "carpentry", "auto diagnostics",
    "Python", "JavaScript", "SQL", "React", "Flask", "Figma", "UX design",
    "data analysis", "project management", "customer service",
]


# ---------------------------------------------------------------- models --
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), default="")
    color = db.Column(db.String(16), default="#2c6e62")
    completion = db.Column(db.Integer, default=72)
    cv_uploaded = db.Column(db.Boolean, default=False)
    skills = db.Column(db.Text, default="")  # comma-separated, from CV extraction
    alumni_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ---- student / alumni academic context ----
    headline = db.Column(db.String(160), default="")
    programme = db.Column(db.String(160), default="")
    year = db.Column(db.String(32), default="")
    campus = db.Column(db.String(120), default="")

    # ---- business profile (brief §2.3) ----
    industry = db.Column(db.String(120), default="")
    company_desc = db.Column(db.Text, default="")
    location = db.Column(db.String(160), default="")
    talent_sought = db.Column(db.Text, default="")

    # ---- portfolio fields ----
    bio = db.Column(db.Text, default="")
    github_url = db.Column(db.String(255), default="")
    linkedin_url = db.Column(db.String(255), default="")
    credly_url = db.Column(db.String(255), default="")
    portfolio_url = db.Column(db.String(255), default="")

    # ---- visibility toggles ----
    profile_visible = db.Column(db.Boolean, default=True)
    show_email = db.Column(db.Boolean, default=False)
    show_skills = db.Column(db.Boolean, default=True)

    # ---- account state ----
    business_approved = db.Column(db.Boolean, default=False)
    suspended = db.Column(db.Boolean, default=False)
    last_seen = db.Column(db.DateTime, nullable=True)

    # ---- onboarding ----
    onboarding_complete = db.Column(db.Boolean, default=False)
    onboarding_step = db.Column(db.Integer, default=0)

    # ---- password reset ----
    reset_token = db.Column(db.String(64), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)

    def to_public(self):
        return {
            "id": self.id, "username": self.username, "role": self.role,
            "name": self.name, "color": self.color,
            "avatarUrl": profile_image_url(self.id),
            "completion": self.completion, "cvUploaded": self.cv_uploaded,
            "skills": [s for s in self.skills.split(",") if s],
            "alumniVerified": self.alumni_verified,
            "bio": self.bio,
            "headline": self.headline, "programme": self.programme,
            "year": self.year, "campus": self.campus,
            "businessApproved": self.business_approved,
            "company": {
                "industry": self.industry, "description": self.company_desc,
                "location": self.location, "talentSought": self.talent_sought,
            },
            "portfolio": {
                "github": self.github_url, "linkedin": self.linkedin_url,
                "credly": self.credly_url, "website": self.portfolio_url,
            },
            "visibility": {
                "profileVisible": self.profile_visible,
                "showEmail": self.show_email,
                "showSkills": self.show_skills,
            },
            "onboarding": {
                "complete": self.onboarding_complete,
                "step": self.onboarding_step,
            },
        }

    def to_profile_view(self, viewer):
        """Public-facing profile as seen by someone else, honouring the
        visibility toggles. `viewer` may be the owner (everything shown)."""
        is_owner = viewer is not None and viewer.id == self.id
        data = {
            "id": self.id, "name": self.name, "role": self.role,
            "color": self.color, "avatarUrl": profile_image_url(self.id),
            "bio": self.bio,
            "headline": self.headline, "programme": self.programme,
            "year": self.year, "campus": self.campus,
            "portfolio": {
                "github": self.github_url, "linkedin": self.linkedin_url,
                "credly": self.credly_url, "website": self.portfolio_url,
            },
        }
        if is_owner or self.show_skills:
            data["skills"] = [s for s in self.skills.split(",") if s]
        if is_owner or self.show_email:
            data["email"] = self.email
        testimonials = Testimonial.query.filter_by(user_id=self.id, approved=True) \
            .order_by(Testimonial.id.desc()).all()
        data["testimonials"] = [t.to_dict() for t in testimonials]
        return data



class ProfileImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    filename = db.Column(db.String(80), nullable=False, unique=True)


def profile_image_url(user_id):
    image = ProfileImage.query.filter_by(user_id=user_id).first()
    return f"/profile-images/{image.filename}" if image else ""


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    feed = db.Column(db.String(16), nullable=False)
    author_name = db.Column(db.String(120), nullable=False)
    author_role = db.Column(db.String(120), nullable=False)
    color = db.Column(db.String(16), default="#2c6e62")
    body = db.Column(db.Text, nullable=False)
    media = db.Column(db.Boolean, default=False)
    video_url = db.Column(db.String(255), default="")
    thumb_url = db.Column(db.String(255), default="")
    pick = db.Column(db.Boolean, default=False)
    flagged = db.Column(db.Boolean, default=False)
    base_likes = db.Column(db.Integer, default=0)
    removed = db.Column(db.Boolean, default=False)

    def to_dict(self, user_id):
        liked = Like.query.filter_by(post_id=self.id, user_id=user_id).first() is not None
        extra_likes = Like.query.filter_by(post_id=self.id).count()
        comments = Comment.query.filter_by(post_id=self.id).order_by(Comment.id).all()
        return {
            "id": self.id, "name": self.author_name, "role": self.author_role,
            "color": self.color, "body": self.body, "media": self.media,
            "videoUrl": self.video_url or None, "thumbUrl": self.thumb_url or None,
            "pick": self.pick, "flagged": self.flagged,
            "likeCount": self.base_likes + extra_likes, "likedByMe": liked,
            "comments": [c.to_dict() for c in comments],
        }


class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("post_id", "user_id"),)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    author_name = db.Column(db.String(120), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"who": self.author_name, "text": self.text}


class Opportunity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    co = db.Column(db.String(160), nullable=False)
    match = db.Column(db.Integer, default=80)
    tags = db.Column(db.String(255), default="")
    owner_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    listing_id = db.Column(db.Integer, db.ForeignKey("business_listing.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self, user_id):
        applied = Application.query.filter_by(opportunity_id=self.id, user_id=user_id).first() is not None
        user = User.query.get(user_id)
        skill_match = compute_match(user, self.tags)
        return {"id": self.id, "title": self.title, "co": self.co,
                "match": skill_match if skill_match is not None else self.match,
                "matchIsFallback": skill_match is None,
                "tags": [t for t in self.tags.split(",") if t], "applied": applied}


class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("opportunity.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("opportunity_id", "user_id"),)


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    place = db.Column(db.String(160), nullable=False)
    day = db.Column(db.String(8), nullable=False)
    mon = db.Column(db.String(8), nullable=False)
    programmes = db.Column(db.String(255), default="")  # CSV; blank = everyone

    def to_dict(self, user_id):
        interested = Interest.query.filter_by(event_id=self.id, user_id=user_id).first() is not None
        return {"id": self.id, "title": self.title, "place": self.place,
                "day": self.day, "mon": self.mon, "programmes": self.programmes,
                "interested": interested}


class Interest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("event_id", "user_id"),)


class Pathway(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prog = db.Column(db.String(160), nullable=False)
    rows = db.Column(db.Text, default="")  # "|" separated

    def to_dict(self):
        return {"id": self.id, "prog": self.prog, "rows": [r for r in self.rows.split("|") if r]}


class NetworkRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(120), nullable=False)
    color = db.Column(db.String(16), default="#2c6e62")
    status = db.Column(db.String(16), default="pending")  # pending/accepted/ignored
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Suggested(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(120), nullable=False)
    color = db.Column(db.String(16), default="#2c6e62")
    status = db.Column(db.String(16), default="none")  # none/pending


class ConnectionNPC(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(120), nullable=False)
    color = db.Column(db.String(16), default="#2c6e62")
    skill = db.Column(db.String(120), default="")
    endorsements = db.Column(db.Integer, default=0)
    endorsed_by_me = db.Column(db.Boolean, default=False)


class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    color = db.Column(db.String(16), default="#2c6e62")
    unread = db.Column(db.Boolean, default=False)

    def to_dict(self):
        msgs = Message.query.filter_by(conversation_id=self.id).order_by(Message.id).all()
        return {"id": self.slug, "name": self.name, "color": self.color,
                "unread": self.unread, "messages": [m.to_dict() for m in msgs]}


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversation.id"), nullable=False)
    who = db.Column(db.String(8), nullable=False)  # 'me' or 'them'
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"who": self.who, "text": self.text}


class AlumniVerification(db.Model):
    """Queue for grads who no longer have an active @richfield/@aaa login."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    document_ref = db.Column(db.String(255), nullable=False)
    note = db.Column(db.Text, default="")
    status = db.Column(db.String(16), default="pending")  # pending/approved/rejected
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        user = User.query.get(self.user_id)
        return {"id": self.id, "userId": self.user_id, "name": user.name if user else "Unknown",
                "documentRef": self.document_ref, "note": self.note, "status": self.status,
                "submittedAt": self.submitted_at.isoformat()}


class ApprovalQueueItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    co = db.Column(db.String(160), nullable=False)
    tags = db.Column(db.String(255), default="")
    status = db.Column(db.String(16), default="pending")
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    decided_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {"id": self.id, "title": self.title, "co": self.co,
                "tags": [t for t in self.tags.split(",") if t], "status": self.status}


class BusinessListing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    queue_item_id = db.Column(db.Integer, db.ForeignKey("approval_queue_item.id"), nullable=True)
    title = db.Column(db.String(160), nullable=False)
    co = db.Column(db.String(160), default="")
    tags = db.Column(db.String(255), default="")
    status = db.Column(db.String(16), default="pending")  # pending/live/rejected
    impressions = db.Column(db.Integer, default=0)

    def to_dict(self):
        # Pipeline + engagement computed live so they never drift.
        pipeline = 0
        for opp in Opportunity.query.filter_by(listing_id=self.id).all():
            pipeline += Application.query.filter_by(opportunity_id=opp.id).count()
        engagement = "—"
        if self.impressions:
            engagement = f"{round(100 * pipeline / self.impressions)}% of {self.impressions} views"
        return {"id": self.id, "title": self.title, "co": self.co,
                "tags": [t for t in self.tags.split(",") if t],
                "status": self.status, "pipeline": pipeline, "engagement": engagement}


class CoachMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    who = db.Column(db.String(8), nullable=False)  # 'ai' or 'user'
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"who": self.who, "text": self.text}


class ProfileView(db.Model):
    """One row per time a logged-in user opens someone else's profile."""
    id = db.Column(db.Integer, primary_key=True)
    viewed_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    viewer_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    source = db.Column(db.String(32), default="profile")  # profile/application/search
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Testimonial(db.Model):
    """A short endorsement left on a user's profile by a connection."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    author_name = db.Column(db.String(120), nullable=False)
    author_role = db.Column(db.String(120), default="")
    text = db.Column(db.Text, nullable=False)
    approved = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "authorName": self.author_name,
                "authorRole": self.author_role, "text": self.text,
                "createdAt": self.created_at.isoformat()}


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    type = db.Column(db.String(32), nullable=False)
    text = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(255), default="")
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "type": self.type, "text": self.text,
                "link": self.link, "read": self.read,
                "createdAt": self.created_at.isoformat()}


class SkillSearch(db.Model):
    """One row per skill term a business searches for. Powers the
    'most searched skills' panel on student analytics dashboards."""
    id = db.Column(db.Integer, primary_key=True)
    skill = db.Column(db.String(120), nullable=False)
    searcher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# -------------------------------------------------- realtime + analytics --
def push_notification(user_id, ntype, text, link=""):
    """Persist a Notification row AND push it live over the socket."""
    note = Notification(user_id=user_id, type=ntype, text=text, link=link)
    db.session.add(note)
    db.session.flush()
    socketio.emit("notification", note.to_dict(), room=f"user:{user_id}")
    return note


def send_email(to_addr, subject, body):
    """Actually deliver mail when SMTP_HOST/PORT/USER/PASS/FROM are set in
    the environment (works with Gmail app-passwords, SendGrid, Mailtrap,
    Resend's SMTP endpoint, etc.). With no SMTP configured — the default
    for this demo — it just logs to the console, same pattern as the
    forgot-password devResetToken fallback above. Callers should never
    assume the send succeeded; this never raises.
    """
    if not to_addr:
        return False
    host = os.environ.get("SMTP_HOST")
    if not host:
        print(f"[email:not-configured] to={to_addr} subject={subject!r}\n{body}\n"
              f"(set SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS/SMTP_FROM to send for real)")
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", ""))
        msg["To"] = to_addr
        port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            user = os.environ.get("SMTP_USER")
            pw = os.environ.get("SMTP_PASS")
            if user and pw:
                server.login(user, pw)
            server.sendmail(msg["From"], [to_addr], msg.as_string())
        return True
    except Exception as exc:  # noqa: BLE001 — a failed email must never break the request
        print(f"[email:failed] to={to_addr} subject={subject!r} error={exc}")
        return False


def notify_user(user_id, event, data):
    socketio.emit(event, data, room=f"user:{user_id}")


def notify_role(role, event, data):
    socketio.emit(event, data, room=f"role:{role}")


def notify_job_match(opportunity):
    """Smart job matching (brief §2.8): only students whose extracted
    skills overlap the listing tags are notified — not a broadcast."""
    tags = {t.strip().lower() for t in (opportunity.tags or "").split(",") if t.strip()}
    if not tags:
        return
    for student in User.query.filter(User.role.in_(STUDENT_ROLES),
                                     User.suspended.is_(False)).all():
        skills = {s.strip().lower() for s in (student.skills or "").split(",") if s.strip()}
        if skills & tags:
            push_notification(student.id, "job_match",
                              f"New opportunity matching your skills: {opportunity.title}",
                              link="discover:opportunities")


def _join_authenticated_socket_rooms():
    """Join only rooms derived from the authenticated Flask session."""
    user = current_user()
    if not user or user.suspended:
        return False
    join_room(f"user:{user.id}")
    join_room(f"role:{user.role}")
    return True


@socketio.on("connect")
def _socket_connect():
    # Reject anonymous and suspended clients before they can subscribe to
    # private realtime events.
    if not _join_authenticated_socket_rooms():
        return False


@socketio.on("join")
def _socket_join(data=None):
    # Kept as a compatibility event for existing clients. Client-supplied
    # identity/role claims are deliberately ignored.
    return _join_authenticated_socket_rooms()


def daily_series(datetimes, days=14):
    """Bucket timestamps into one count per day for the sparkline charts."""
    today = datetime.utcnow().date()
    buckets = {today - timedelta(days=i): 0 for i in range(days - 1, -1, -1)}
    for dt in datetimes:
        if dt and dt.date() in buckets:
            buckets[dt.date()] += 1
    return [{"date": d.isoformat(), "count": c} for d, c in buckets.items()]


def cumulative(series):
    running, out = 0, []
    for point in series:
        running += point["count"]
        out.append({"date": point["date"], "count": running})
    return out


def recalc_completion(user):
    """Completeness derived from what's actually filled in."""
    checks = [
        bool((user.bio or "").strip()),
        bool((user.email or "").strip()),
        bool((user.headline or "").strip()),
        bool((user.programme or "").strip()),
        bool((user.skills or "").strip()),
        bool((user.github_url or "").strip()),
        bool((user.linkedin_url or "").strip()),
        bool((user.credly_url or "").strip()),
        bool((user.portfolio_url or "").strip()),
        user.cv_uploaded,
    ]
    user.completion = round(100 * sum(checks) / len(checks))


# --------------------------------------------------------- job matching --
def compute_match(user, tags_csv):
    """Skill-overlap match score. Falls back to the static seed score when
    the user has no extracted skills yet, so a new profile never shows 0%."""
    opp_tags = {t.strip().lower() for t in tags_csv.split(",") if t.strip()}
    user_skills = {s.strip().lower() for s in (user.skills if user else "").split(",") if s.strip()}
    if not user_skills or not opp_tags:
        return None
    overlap = len(opp_tags & user_skills)
    if overlap == 0:
        return 40
    return min(97, 55 + overlap * 15)


# --------------------------------------------------------- CV extraction --
def extract_skills(cv_text):
    """Keyword match against SKILL_VOCAB. spaCy's model download isn't on
    this sandbox's network allow-list; this is dependency-free and a
    drop-in swap for spaCy's PhraseMatcher later (same input/output)."""
    low = (cv_text or "").lower()
    return [skill for skill in SKILL_VOCAB if skill.lower() in low]


# ------------------------------------------------------------- coach ai --
CHAT_REPLIES = [
    (["photo", "picture", "image"],
     "A clear headshot — and one photo of recent work — go a long way. Profiles with both "
     "show up in business searches about 3x more often. Want help writing a caption?"),
    (["skill", "skills"],
     "List the specific skills you actually used on a job, not just your trade title — "
     "'MIG welding' and 'blueprint reading' get matched far more precisely than just 'Welder'."),
    (["video", "post"],
     "Short clips of you mid-task — fitting a panel, hemming a garment, debugging live — tend to "
     "outperform text posts. Even 15 seconds is enough."),
    (["cv", "resume", "document"],
     "Head to your Profile tab and tap 'Upload CV' — I'll pull out your skills, qualifications "
     "and experience automatically so you don't have to retype everything."),
    (["connect", "network"],
     "Start with people from your own cohort or workshop, then follow two or three alumni in the "
     "career you want — check your Network tab for suggestions already lined up."),
    (["listing", "post a job", "hire"],
     "Listings with 4+ specific skill tags get matched to relevant candidates automatically — "
     "vague titles like 'General worker' get far less reach."),
    (["flag", "moderation", "review"],
     "You've got items in your moderation queue and a business pending verification. I'd clear "
     "the verification first — it's blocking a live listing."),
]


def rule_based_reply(role, text):
    low = text.lower()
    for keywords, answer in CHAT_REPLIES:
        if any(k in low for k in keywords):
            return answer
    if role == "business":
        return ("Your strongest lever right now is finishing your company profile — listings from "
                "complete profiles get roughly 2x the applicant volume.")
    if role == "admin":
        return ("Platform health looks steady. The approval queue is your highest-leverage task — "
                "pending listings lose about 20% of their relevance for every day they wait.")
    return ("Good question. Based on your profile, the highest-impact next step is finishing your "
            "skills section — it's the field business users filter by most.")


ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
COACH_SYSTEM_PROMPT = (
    "You are the Forge career coach, embedded in a networking platform for tradespeople, "
    "graduates, businesses and campus admins. Give short (2-4 sentence), specific, practical "
    "career-development advice for the user's role ({role}). No markdown, no headers."
)


def llm_reply(role, history):
    """Real LLM call; falls back to rule-based replies when no key is set
    or the request fails, so the demo never breaks."""
    if not ANTHROPIC_API_KEY:
        return None
    messages = [{"role": ("assistant" if m.who == "ai" else "user"), "content": m.text} for m in history]
    payload = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 300,
        "system": COACH_SYSTEM_PROMPT.format(role=role),
        "messages": messages,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "content-type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
        blocks = [b.get("text", "") for b in body.get("content", []) if b.get("type") == "text"]
        text = "\n".join(blocks).strip()
        return text or None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return None


def reply_for(role, text, history=None):
    reply = llm_reply(role, history) if history is not None else None
    return reply if reply is not None else rule_based_reply(role, text)


# ------------------------------------------------------------- helpers --
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return User.query.get(uid)


def require_login():
    uid = session.get("user_id")
    if not uid:
        return None, (jsonify({"error": "not authenticated"}), 401)
    user = User.query.get(uid)
    if not user:
        session.pop("user_id", None)
        _clear_csrf_token()
        return None, (jsonify({"error": "not authenticated"}), 401)
    if user.suspended:
        return None, (jsonify({"error": "account suspended — contact the administrator"}), 403)
    user.last_seen = datetime.utcnow()   # cheap MAU signal for admin analytics
    db.session.commit()
    return user, None


def _clear_csrf_token():
    session.pop("csrf_token", None)
    session.pop("csrf_user_id", None)


def _set_authenticated_session(user):
    session["user_id"] = user.id
    # Rotate even when the same account signs in again.
    session["csrf_token"] = secrets.token_urlsafe(32)
    session["csrf_user_id"] = user.id


def _http_origin(value, *, referer=False):
    """Return a normalized (scheme, host, port), rejecting ambiguous URLs."""
    if not value or any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
        return None
    try:
        url = urlsplit(value)
        if (url.scheme not in ("http", "https") or not url.hostname
                or url.username is not None or url.password is not None
                or url.fragment or (not referer and (url.path or url.query))):
            return None
        port = url.port if url.port is not None else (443 if url.scheme == "https" else 80)
        return url.scheme, url.hostname.lower(), port
    except ValueError:
        return None


@app.before_request
def protect_cookie_api_requests():
    # Anonymous login/register/reset requests keep their existing behavior.
    # Authenticated calls to those same routes are protected too.
    if (not request.path.startswith("/api/")
            or request.method in ("GET", "HEAD", "OPTIONS", "TRACE")
            or not session.get("user_id")):
        return None

    # Use only the direct WSGI scheme and Host; never trust forwarded headers.
    target = _http_origin(f"{request.scheme}://{request.host}")
    if "Origin" in request.headers:
        source = _http_origin(request.headers["Origin"])
    else:
        source = _http_origin(request.headers.get("Referer"), referer=True)
    if target is None or source is None or source != target:
        return jsonify({"error": "same-origin request required", "code": "csrf_failed"}), 403

    expected = session.get("csrf_token")
    supplied = request.headers.get("X-CSRF-Token", "")
    if (session.get("csrf_user_id") != session["user_id"]
            or not isinstance(expected, str) or not expected or not supplied
            or not secrets.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8"))):
        return jsonify({"error": "valid CSRF token required", "code": "csrf_failed"}), 403
    return None


@app.get("/api/auth/csrf-token")
def csrf_token():
    user, err = require_login()
    if err:
        return err
    if not session.get("csrf_token") or session.get("csrf_user_id") != user.id:
        session["csrf_token"] = secrets.token_urlsafe(32)
        session["csrf_user_id"] = user.id
    response = jsonify({"csrfToken": session["csrf_token"]})
    response.headers["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------- auth --
# In-memory brute-force guard — fine for a demo; use flask-limiter +
# Redis before production.
_failed_logins = defaultdict(list)
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 300


def email_domain_ok(email):
    email = (email or "").strip().lower()
    if "@" not in email:
        return False
    domain = email.rsplit("@", 1)[1]
    return any(domain == d or domain.endswith("." + d) for d in ALLOWED_STUDENT_DOMAINS)


@app.post("/api/auth/register")
def register():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = data.get("role") or "grad"
    name = (data.get("name") or username).strip()
    email = (data.get("email") or "").strip()
    if not username or not password or role not in SELF_REGISTER_ROLES:
        return jsonify({"error": "username, password and a valid role are required"}), 400
    if role in STUDENT_ROLES and email and not email_domain_ok(email):
        return jsonify({
            "error": "student accounts must use a Richfield or AAA institutional email "
                     "(e.g. name@my.richfield.ac.za), or leave it blank and use alumni "
                     "verification instead",
        }), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "username already taken"}), 409
    user = User(username=username, password_hash=generate_password_hash(password),
                role=role, name=name, email=email)
    db.session.add(user)
    db.session.commit()
    seed_coach_intro(user)
    _set_authenticated_session(user)
    return jsonify(user.to_public()), 201


@app.post("/api/admin/provision")
def provision_admin():
    """Create an admin account. Not reachable via the public register form.
    Gated by a server-side secret; a wrong/missing secret returns 404 so
    the route's existence isn't revealed to a casual prober."""
    provision_secret = os.environ.get("FORGE_ADMIN_PROVISION_SECRET", "")
    supplied = request.headers.get("X-Provision-Secret", "")
    if not provision_secret or supplied != provision_secret:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    name = (data.get("name") or username).strip()
    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "username already taken"}), 409
    user = User(username=username, password_hash=generate_password_hash(password),
                role="admin", name=name)
    db.session.add(user)
    db.session.commit()
    seed_coach_intro(user)
    return jsonify(user.to_public()), 201


@app.post("/api/auth/login")
def login():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    now = time.time()
    recent_failures = [t for t in _failed_logins[username] if now - t < LOGIN_LOCKOUT_SECONDS]
    if len(recent_failures) >= LOGIN_MAX_ATTEMPTS:
        return jsonify({"error": "too many attempts — try again in a few minutes"}), 429

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        recent_failures.append(now)
        _failed_logins[username] = recent_failures
        return jsonify({"error": "invalid credentials"}), 401
    if user.suspended:
        return jsonify({"error": "this account has been suspended"}), 403
    _failed_logins.pop(username, None)
    _set_authenticated_session(user)
    user.last_seen = datetime.utcnow()
    db.session.commit()
    # Sign-in alert: always logged as an in-app notification; also a real
    # email when the account has one and SMTP is configured (brief §2.1 —
    # this isn't a mandatory feature, just good account-security practice).
    push_notification(user.id, "security", "New sign-in to your Forge account.")
    if user.email:
        send_email(user.email, "New sign-in to your Forge account",
                   f"Hi {user.name},\n\nYour Forge account was just signed in to. "
                   f"If this wasn't you, reset your password immediately from the "
                   f"login screen.\n\n— Forge")
    return jsonify(user.to_public())


@app.post("/api/auth/forgot-password")
def forgot_password():
    """Issue a password-reset token. This demo has no email/SMTP service
    wired up, so in debug mode the token is returned directly in the
    response for the UI to use. In non-debug mode the token is never
    returned to the client — wire up real email delivery before then.
    Response is deliberately the same either way so the endpoint can't be
    used to check which usernames exist."""
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    user = User.query.filter_by(username=username).first()
    token = None
    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_token_expires = datetime.utcnow() + timedelta(minutes=30)
        db.session.commit()
        if user.email:
            reset_url = f"{request.host_url.rstrip('/')}/?resetToken={token}"
            send_email(user.email, "Reset your Forge password",
                       f"Hi {user.name},\n\nSomeone requested a password reset for your "
                       f"Forge account. This link expires in 30 minutes:\n\n{reset_url}\n\n"
                       f"If you didn't request this, you can ignore this email.\n\n— Forge")
        push_notification(user.id, "security", "A password reset was requested for your account.")
    resp = {"message": "If that account exists, password reset instructions are on their way."}
    if app.debug and token:
        resp["devResetToken"] = token
    return jsonify(resp)


@app.post("/api/auth/reset-password")
def reset_password():
    data = request.get_json(force=True) or {}
    token = (data.get("token") or "").strip()
    new_password = data.get("newPassword") or ""
    if not token or not new_password:
        return jsonify({"error": "token and newPassword are required"}), 400
    if len(new_password) < 8:
        return jsonify({"error": "password must be at least 8 characters"}), 400
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_token_expires or user.reset_token_expires < datetime.utcnow():
        return jsonify({"error": "that reset link is invalid or has expired"}), 400
    user.password_hash = generate_password_hash(new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.session.commit()
    push_notification(user.id, "security", "Your password was changed.")
    if user.email:
        send_email(user.email, "Your Forge password was changed",
                   f"Hi {user.name},\n\nYour Forge password was just changed. If you didn't "
                   f"do this, contact your campus admin immediately.\n\n— Forge")
    return jsonify({"message": "Password updated — you can sign in now."})


@app.post("/api/auth/demo-login")
def demo_login():
    """Explicit local-development demo convenience, disabled by default."""
    if not app.config.get("FORGE_DEMO_MODE", False):
        return jsonify({"error": "not available"}), 404
    data = request.get_json(force=True) or {}
    role = data.get("role")
    if role not in ROLES:
        return jsonify({"error": "unknown role"}), 400
    user = User.query.filter_by(username=f"demo_{role}").first()
    if not user:
        return jsonify({"error": "demo user missing - run seed"}), 500
    _set_authenticated_session(user)
    return jsonify(user.to_public())


@app.post("/api/auth/logout")
def logout():
    session.pop("user_id", None)
    _clear_csrf_token()
    return jsonify({"ok": True})


@app.get("/api/auth/me")
def me():
    user = current_user()
    return jsonify(user.to_public() if user else None)


# ---------------------------------------------------------------- feed --
@app.get("/api/feed")
def get_feed():
    user, err = require_login()
    if err:
        return err
    posts = Post.query.filter_by(feed=user.role, removed=False).all()

    def relevance(post):
        # Engagement-ranked feed (brief §2.4): likes + weighted comments,
        # editor picks rise, flagged content sinks until an admin acts.
        likes = post.base_likes + Like.query.filter_by(post_id=post.id).count()
        comments = Comment.query.filter_by(post_id=post.id).count()
        return likes + 2 * comments + (6 if post.pick else 0) - (100 if post.flagged else 0)

    posts.sort(key=relevance, reverse=True)
    return jsonify([p.to_dict(user.id) for p in posts])


@app.post("/api/posts")
def create_post():
    user, err = require_login()
    if err:
        return err
    body = (request.get_json(force=True) or {}).get("body", "").strip()
    if not body:
        return jsonify({"error": "body required"}), 400
    post = Post(feed=user.role, author_name=user.name, author_role=user.role,
                color=user.color, body=body)
    db.session.add(post)
    db.session.commit()
    return jsonify(post.to_dict(user.id)), 201


@app.post("/api/posts/<int:post_id>/like")
def toggle_like(post_id):
    user, err = require_login()
    if err:
        return err
    post = Post.query.get_or_404(post_id)
    existing = Like.query.filter_by(post_id=post.id, user_id=user.id).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(Like(post_id=post.id, user_id=user.id))
    db.session.commit()
    return jsonify(post.to_dict(user.id))


@app.post("/api/posts/<int:post_id>/comments")
def add_comment(post_id):
    user, err = require_login()
    if err:
        return err
    post = Post.query.get_or_404(post_id)
    text = (request.get_json(force=True) or {}).get("text", "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    db.session.add(Comment(post_id=post.id, author_name=user.name, text=text))
    db.session.commit()
    result = post.to_dict(user.id)
    notify_role(post.feed, "new_comment", {"postId": post.id, "post": result})
    return jsonify(result)


@app.delete("/api/posts/<int:post_id>")
def remove_post(post_id):
    user, err = require_login()
    if err:
        return err
    if user.role != "admin":
        return jsonify({"error": "admin only"}), 403
    post = Post.query.get_or_404(post_id)
    post.removed = True
    db.session.commit()
    return jsonify({"ok": True})


@app.post("/api/posts/<int:post_id>/flag")
def flag_post(post_id):
    """Any logged-in user can flag a post for admin review."""
    user, err = require_login()
    if err:
        return err
    post = Post.query.get_or_404(post_id)
    post.flagged = True
    db.session.commit()
    return jsonify(post.to_dict(user.id))


# --------------------------------------------------------------- video --
PLACEHOLDER_THUMB = (
    "<svg xmlns='http://www.w3.org/2000/svg' width='480' height='270'>"
    "<rect width='100%' height='100%' fill='#1e4f46'/>"
    "<text x='50%' y='52%' fill='#f4ede0' font-family='sans-serif' "
    "font-size='24' text-anchor='middle'>Forge video</text></svg>"
)


def _video_container_family(header):
    """Identify the supported container family from file bytes."""
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "iso-bmff"
    if header.startswith(b"\\x1a\\x45\\xdf\\xa3"):
        return "ebml"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"AVI ":
        return "avi"
    return None


def _video_content_matches_extension(file_storage, ext):
    """Reject extension-only uploads; require a matching container signature."""
    try:
        header = file_storage.stream.read(4096)
        file_storage.stream.seek(0)
    except (OSError, ValueError):
        return False
    return _video_container_family(header) == VIDEO_CONTAINER_FAMILIES.get(ext)


def _save_video_bounded(file_storage, destination):
    """Copy at most MAX_VIDEO_BYTES to a new file; never overwrite an existing path."""
    total = 0
    try:
        with open(destination, "xb") as output:
            while True:
                remaining = MAX_VIDEO_BYTES - total
                chunk = file_storage.stream.read(min(1024 * 1024, remaining + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_VIDEO_BYTES:
                    raise ValueError("video larger than 50MB")
                output.write(chunk)
    except Exception:
        try:
            os.remove(destination)
        except FileNotFoundError:
            pass
        raise
    return total


def _remove_media_artifact(path):
    if not path:
        return
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def process_video(src_path, base_name):
    """Transcode and thumbnail a validated upload when ffmpeg is available.

    A configured ffmpeg failure is treated as invalid/unprocessable media
    instead of silently publishing the original. Without ffmpeg, the
    signature-validated original is retained with a generated placeholder.
    """
    thumb_path = os.path.join(UPLOAD_DIR, base_name + "_thumb.svg")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        with open(thumb_path, "x", encoding="utf-8") as fh:
            fh.write(PLACEHOLDER_THUMB)
        return src_path, thumb_path

    transcoded = os.path.join(UPLOAD_DIR, base_name + "_web.mp4")
    jpg_thumb = os.path.join(UPLOAD_DIR, base_name + "_thumb.jpg")
    try:
        subprocess.run(
            [ffmpeg, "-y", "-i", src_path,
             "-vf", "scale='min(1280,iw)':-2",
             "-c:v", "libx264", "-crf", "26", "-preset", "veryfast",
             "-c:a", "aac", "-b:a", "96k",
             "-movflags", "+faststart", transcoded],
            check=True, capture_output=True, timeout=180)
        subprocess.run(
            [ffmpeg, "-y", "-ss", "1", "-i", transcoded,
             "-frames:v", "1", "-vf", "scale=480:-2", jpg_thumb],
            check=True, capture_output=True, timeout=60)
    except (subprocess.SubprocessError, OSError) as exc:
        _remove_media_artifact(transcoded)
        _remove_media_artifact(jpg_thumb)
        raise ValueError("video could not be safely processed") from exc

    os.remove(src_path)
    return transcoded, jpg_thumb


@app.post("/api/posts/video")
def upload_video_post():
    user, err = require_login()
    if err:
        return err
    if user.role not in STUDENT_ROLES:
        return jsonify({"error": "only students and alumni can post videos"}), 403

    # Check the complete multipart request before parsing request.files.
    if request.content_length and request.content_length > MAX_VIDEO_REQUEST_BYTES:
        return jsonify({"error": "video larger than 50MB"}), 413

    file = request.files.get("video")
    if not file or not file.filename:
        return jsonify({"error": "video file required"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        return jsonify({"error": f"unsupported video type {ext}"}), 400

    if not _video_content_matches_extension(file, ext):
        return jsonify({"error": "video content does not match a supported container"}), 415

    caption = (request.form.get("caption") or "Shared a video").strip()
    safe_stem = secure_filename(os.path.splitext(file.filename)[0]) or "video"
    base_name = f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{safe_stem}"
    src_path = os.path.join(UPLOAD_DIR, base_name + ext)

    try:
        _save_video_bounded(file, src_path)
        stored, thumb = process_video(src_path, base_name)
    except ValueError as exc:
        _remove_media_artifact(src_path)
        status = 413 if str(exc) == "video larger than 50MB" else 400
        return jsonify({"error": str(exc)}), status

    post = Post(feed=user.role, author_name=user.name, author_role=user.role,
                color=user.color, body=caption, media=True,
                video_url=f"/uploads/{os.path.basename(stored)}",
                thumb_url=f"/uploads/{os.path.basename(thumb)}")
    db.session.add(post)
    db.session.commit()
    return jsonify(post.to_dict(user.id)), 201


@app.get("/uploads/<path:name>")
def serve_upload(name):
    user, err = require_login()
    if err:
        return err

    # Forge generates flat filenames. Reject nested paths even though
    # send_from_directory also performs traversal protection.
    if not name or name != os.path.basename(name):
        abort(404)

    media_url = f"/uploads/{name}"
    post = (Post.query
            .filter_by(media=True, removed=False)
            .filter((Post.video_url == media_url) | (Post.thumb_url == media_url))
            .first())
    if not post:
        abort(404)

    # Media inherits the same role-feed boundary as /api/feed. Admins retain
    # access to active media for moderation.
    if user.role != "admin" and post.feed != user.role:
        abort(404)

    response = send_from_directory(UPLOAD_DIR, name, conditional=True)
    response.headers["Cache-Control"] = "private, max-age=86400"
    return response


# ----------------------------------------------------------- discover --
@app.get("/api/opportunities")
def get_opportunities():
    user, err = require_login()
    if err:
        return err
    opps = Opportunity.query.order_by(Opportunity.id).all()
    # Count an impression against the source listing when a student
    # browses the board — powers the business engagement-rate metric.
    if user.role in STUDENT_ROLES:
        listing_ids = [o.listing_id for o in opps if o.listing_id]
        if listing_ids:
            BusinessListing.query.filter(BusinessListing.id.in_(listing_ids)) \
                .update({"impressions": BusinessListing.impressions + 1},
                        synchronize_session=False)
            db.session.commit()
    return jsonify([o.to_dict(user.id) for o in opps])


@app.post("/api/opportunities/<int:opp_id>/apply")
def toggle_apply(opp_id):
    user, err = require_login()
    if err:
        return err
    opp = Opportunity.query.get_or_404(opp_id)
    existing = Application.query.filter_by(opportunity_id=opp.id, user_id=user.id).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(Application(opportunity_id=opp.id, user_id=user.id))
        if opp.owner_user_id:
            db.session.add(ProfileView(viewed_user_id=user.id, viewer_user_id=opp.owner_user_id,
                                       source="application"))
            push_notification(opp.owner_user_id, "applicant",
                              f"{user.name} applied to {opp.title}", link="business:listings")
            notify_user(opp.owner_user_id, "new_applicant",
                        {"opportunityId": opp.id, "applicant": user.name})
    db.session.commit()
    return jsonify(opp.to_dict(user.id))


@app.get("/api/events")
def get_events():
    user, err = require_login()
    if err:
        return err
    return jsonify([e.to_dict(user.id) for e in Event.query.order_by(Event.id).all()])


@app.post("/api/admin/events")
def create_event():
    """Institutional events are admin-published only. Optionally target
    specific programmes; matching students get notified."""
    user, err = require_login()
    if err:
        return err
    if user.role != "admin":
        return jsonify({"error": "admin only"}), 403
    data = request.get_json(force=True) or {}
    title = (data.get("title") or "").strip()
    place = (data.get("place") or "").strip()
    day = (data.get("day") or "").strip()
    mon = (data.get("mon") or "").strip()
    if not all([title, place, day, mon]):
        return jsonify({"error": "title, place, day and mon are required"}), 400
    programmes = [p.strip().lower() for p in (data.get("programmes") or "").split(",") if p.strip()]
    event = Event(title=title, place=place, day=day, mon=mon, programmes=",".join(programmes))
    db.session.add(event)
    db.session.commit()
    for target in User.query.filter(User.role.in_(STUDENT_ROLES)).all():
        if not programmes or (target.programme or "").lower() in programmes:
            push_notification(target.id, "event", f"New event: {title} — {place}",
                              link="discover:events")
    return jsonify(event.to_dict(user.id)), 201


@app.post("/api/events/<int:event_id>/interest")
def toggle_interest(event_id):
    user, err = require_login()
    if err:
        return err
    event = Event.query.get_or_404(event_id)
    existing = Interest.query.filter_by(event_id=event.id, user_id=user.id).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(Interest(event_id=event.id, user_id=user.id))
    db.session.commit()
    return jsonify(event.to_dict(user.id))


@app.get("/api/pathways")
def get_pathways():
    _, err = require_login()
    if err:
        return err
    return jsonify([p.to_dict() for p in Pathway.query.order_by(Pathway.id).all()])


# -------------------------------------------------------- business side --
@app.get("/api/business/listings")
def get_business_listings():
    user, err = require_login()
    if err:
        return err
    query = BusinessListing.query
    if user.role == "business":
        query = query.filter_by(owner_user_id=user.id)
    elif user.role != "admin":
        return jsonify({"error": "business or admin only"}), 403
    return jsonify([b.to_dict() for b in query.order_by(BusinessListing.id).all()])


@app.post("/api/business/listings")
def create_listing():
    """A business posts a listing — NOT visible to students until an
    admin approves it (brief §2.5)."""
    user, err = require_login()
    if err:
        return err
    if user.role != "business":
        return jsonify({"error": "business accounts only"}), 403
    if not user.business_approved:
        return jsonify({"error": "your business account is pending admin verification"}), 403
    data = request.get_json(force=True) or {}
    title = (data.get("title") or "").strip()
    tags = (data.get("tags") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    queue_item = ApprovalQueueItem(title=title, co=user.name, tags=tags, status="pending")
    db.session.add(queue_item)
    db.session.flush()
    listing = BusinessListing(owner_user_id=user.id, queue_item_id=queue_item.id,
                              title=title, co=user.name, tags=tags, status="pending")
    db.session.add(listing)
    db.session.commit()
    return jsonify(listing.to_dict()), 201


@app.get("/api/admin/queue")
def get_admin_queue():
    user, err = require_login()
    if err:
        return err
    if user.role != "admin":
        return jsonify({"error": "admin only"}), 403
    return jsonify([q.to_dict() for q in ApprovalQueueItem.query.order_by(ApprovalQueueItem.id).all()])


@app.post("/api/admin/queue/<int:item_id>/<string:action>")
def act_on_queue(item_id, action):
    user, err = require_login()
    if err:
        return err
    if user.role != "admin":
        return jsonify({"error": "admin only"}), 403
    if action not in ("approve", "reject"):
        return jsonify({"error": "unknown action"}), 400
    item = ApprovalQueueItem.query.get_or_404(item_id)
    item.status = "approved" if action == "approve" else "rejected"
    item.decided_at = datetime.utcnow()
    linked_listing = BusinessListing.query.filter_by(queue_item_id=item.id).first()
    new_opportunity = None
    if linked_listing:
        linked_listing.status = "live" if action == "approve" else "rejected"
        if action == "approve":
            new_opportunity = Opportunity(title=item.title, co=item.co, tags=item.tags,
                                          owner_user_id=linked_listing.owner_user_id,
                                          listing_id=linked_listing.id)
            db.session.add(new_opportunity)
        if linked_listing.owner_user_id:
            verb = "approved and is now live" if action == "approve" else "was not approved"
            push_notification(linked_listing.owner_user_id, "approval",
                              f"Your listing \"{item.title}\" {verb}.", link="business:listings")
    db.session.commit()
    if new_opportunity:
        notify_job_match(new_opportunity)
    return jsonify(item.to_dict())


# -------------------------------------------------------- alumni verify --
@app.post("/api/alumni/verify")
def submit_alumni_verification():
    """A grad without a live institutional email proves identity with a
    document instead; an admin is the final approver."""
    user, err = require_login()
    if err:
        return err
    if user.role != "grad":
        return jsonify({"error": "alumni verification is for grad accounts"}), 403
    data = request.get_json(force=True) or {}
    document_ref = (data.get("documentRef") or "").strip()
    note = (data.get("note") or "").strip()
    if not document_ref:
        return jsonify({"error": "documentRef required"}), 400
    record = AlumniVerification(user_id=user.id, document_ref=document_ref, note=note)
    db.session.add(record)
    db.session.commit()
    return jsonify(record.to_dict()), 201


@app.get("/api/admin/alumni-verifications")
def list_alumni_verifications():
    user, err = require_login()
    if err:
        return err
    if user.role != "admin":
        return jsonify({"error": "admin only"}), 403
    return jsonify([v.to_dict() for v in AlumniVerification.query.order_by(AlumniVerification.id).all()])


@app.post("/api/admin/alumni-verifications/<int:record_id>/<string:action>")
def act_on_alumni_verification(record_id, action):
    user, err = require_login()
    if err:
        return err
    if user.role != "admin":
        return jsonify({"error": "admin only"}), 403
    if action not in ("approve", "reject"):
        return jsonify({"error": "unknown action"}), 400
    record = AlumniVerification.query.get_or_404(record_id)
    record.status = "approved" if action == "approve" else "rejected"
    target = User.query.get(record.user_id)
    if target:
        if action == "approve":
            target.alumni_verified = True
        verb = "approved" if action == "approve" else "rejected — please resubmit with a clearer document"
        push_notification(target.id, "verification", f"Your alumni verification was {verb}.")
    db.session.commit()
    return jsonify(record.to_dict())


# ------------------------------------------------------------ network --
@app.get("/api/network")
def get_network():
    _, err = require_login()
    if err:
        return err
    return jsonify({
        "requests": [{"id": r.id, "name": r.name, "role": r.role, "color": r.color, "status": r.status}
                     for r in NetworkRequest.query.order_by(NetworkRequest.id).all()],
        "suggested": [{"id": s.id, "name": s.name, "role": s.role, "color": s.color, "status": s.status}
                      for s in Suggested.query.order_by(Suggested.id).all()],
        "connections": [{"id": c.id, "name": c.name, "role": c.role, "color": c.color,
                         "skill": c.skill, "endorsements": c.endorsements,
                         "endorsedByMe": c.endorsed_by_me}
                        for c in ConnectionNPC.query.order_by(ConnectionNPC.id).all()],
    })


@app.post("/api/network/requests/<int:req_id>/<string:action>")
def handle_request(req_id, action):
    user, err = require_login()
    if err:
        return err
    if action not in ("accept", "ignore"):
        return jsonify({"error": "unknown action"}), 400
    r = NetworkRequest.query.get_or_404(req_id)
    r.status = "accepted" if action == "accept" else "ignored"
    if action == "accept":
        push_notification(user.id, "connection", f"You're now connected with {r.name}.")
    db.session.commit()
    return jsonify({"ok": True})


@app.post("/api/network/suggested/<int:sug_id>/connect")
def connect_suggested(sug_id):
    _, err = require_login()
    if err:
        return err
    s = Suggested.query.get_or_404(sug_id)
    s.status = "pending"
    db.session.commit()
    return jsonify({"ok": True})


@app.post("/api/network/connections/<int:conn_id>/endorse")
def endorse_connection(conn_id):
    _, err = require_login()
    if err:
        return err
    c = ConnectionNPC.query.get_or_404(conn_id)
    c.endorsed_by_me = not c.endorsed_by_me
    c.endorsements += 1 if c.endorsed_by_me else -1
    db.session.commit()
    return jsonify({"id": c.id, "endorsements": c.endorsements, "endorsedByMe": c.endorsed_by_me})


# ---------------------------------------------------------------- chat --
AUTO_REPLIES = (
    "Got it — I'll follow up shortly.",
    "Thanks for the message — let me check and come back to you.",
    "Noted. I'll send the details over this afternoon.",
    "Good question — let me put something together for you.",
)


@app.get("/api/conversations")
def get_conversations():
    _, err = require_login()
    if err:
        return err
    return jsonify([c.to_dict() for c in Conversation.query.order_by(Conversation.id).all()])


@app.get("/api/conversations/<string:slug>")
def get_conversation(slug):
    _, err = require_login()
    if err:
        return err
    convo = Conversation.query.filter_by(slug=slug).first_or_404()
    convo.unread = False
    db.session.commit()
    return jsonify(convo.to_dict())


@app.post("/api/conversations/<string:slug>/messages")
def post_message(slug):
    user, err = require_login()
    if err:
        return err
    text = (request.get_json(force=True) or {}).get("text", "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    convo = Conversation.query.filter_by(slug=slug).first_or_404()
    db.session.add(Message(conversation_id=convo.id, who="me", text=text))
    prior = Message.query.filter_by(conversation_id=convo.id).count()
    db.session.add(Message(conversation_id=convo.id, who="them",
                           text=AUTO_REPLIES[prior % len(AUTO_REPLIES)]))
    db.session.commit()
    result = convo.to_dict()
    notify_user(user.id, "new_message", {"conversationId": slug, "conversation": result})
    return jsonify(result)


# --------------------------------------------------------------- coach --
def seed_coach_intro(user):
    intros = {
        "trade": ["Hi {n} — I'm your Forge coach. I noticed you haven't added a project photo yet. Want a quick tip?",
                  "Profiles with at least one project photo get searched by businesses 3x more often."],
        "grad": ["Hi {n} — your GitHub link isn't on your profile yet. Adding it usually boosts recruiter views."],
        "business": ["Hi {n} — your latest listing is performing well. Want tips to improve the new one?"],
        "admin": ["Morning — you have items pending approval and a flagged post. Want a summary?"],
    }
    for text in intros.get(user.role, []):
        db.session.add(CoachMessage(user_id=user.id, who="ai", text=text.format(n=user.name.split(" ")[0])))
    db.session.commit()


@app.get("/api/coach/chat")
def get_chat():
    user, err = require_login()
    if err:
        return err
    msgs = CoachMessage.query.filter_by(user_id=user.id).order_by(CoachMessage.id).all()
    return jsonify([m.to_dict() for m in msgs])


@app.post("/api/coach/chat")
def post_chat():
    user, err = require_login()
    if err:
        return err
    text = (request.get_json(force=True) or {}).get("text", "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    db.session.add(CoachMessage(user_id=user.id, who="user", text=text))
    db.session.flush()
    history = CoachMessage.query.filter_by(user_id=user.id).order_by(CoachMessage.id).all()
    answer = reply_for(user.role, text, history=history)
    db.session.add(CoachMessage(user_id=user.id, who="ai", text=answer))
    db.session.commit()
    msgs = CoachMessage.query.filter_by(user_id=user.id).order_by(CoachMessage.id).all()
    return jsonify([m.to_dict() for m in msgs])


# -------------------------------------------------------------- profile --
def _profile_image_path(filename):
    if not filename or not PROFILE_IMAGE_NAME_RE.fullmatch(filename):
        return None
    return os.path.join(PROFILE_IMAGE_DIR, filename)


def _unlink_profile_image(filename):
    path = _profile_image_path(filename)
    if not path:
        return
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _decode_profile_image(raw, expected_format):
    """Validate real image bytes and return a canonical square JPEG."""
    try:
        with Image.open(BytesIO(raw)) as probe:
            source_format = (probe.format or "").upper()
            width, height = probe.size

            if source_format != expected_format:
                raise ValueError("image MIME type does not match image data")

            if width <= 0 or height <= 0 or width * height > MAX_PROFILE_IMAGE_PIXELS:
                raise ValueError("image dimensions are too large")

            probe.verify()

        with Image.open(BytesIO(raw)) as source:
            source = ImageOps.exif_transpose(source)
            source = ImageOps.fit(
                source.convert("RGB"),
                PROFILE_IMAGE_SIZE,
                method=Image.Resampling.LANCZOS,
            )
            output = BytesIO()
            source.save(output, format="JPEG", quality=88, optimize=True)
            return output.getvalue()

    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ) as exc:
        raise ValueError(str(exc) or "invalid image") from exc


@app.post("/api/profile/image")
def upload_profile_image():
    user, err = require_login()
    if err:
        return err

    if request.content_length and request.content_length > MAX_PROFILE_IMAGE_REQUEST_BYTES:
        return jsonify({"error": "profile image must be 10MB or smaller"}), 413

    uploaded = request.files.get("image")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "image file required"}), 400

    expected_format = PROFILE_IMAGE_MIME_FORMATS.get(
        (uploaded.mimetype or "").lower()
    )
    if not expected_format:
        return jsonify({
            "error": "profile images must be JPEG, PNG or WebP"
        }), 415

    raw = uploaded.stream.read(MAX_PROFILE_IMAGE_BYTES + 1)

    if len(raw) > MAX_PROFILE_IMAGE_BYTES:
        return jsonify({"error": "profile image must be 10MB or smaller"}), 413

    if not raw:
        return jsonify({"error": "image file required"}), 400

    try:
        canonical = _decode_profile_image(raw, expected_format)
    except ValueError:
        return jsonify({
            "error": "uploaded file is not a valid supported image"
        }), 400

    filename = f"profile_{uuid.uuid4().hex}.jpg"
    path = _profile_image_path(filename)

    try:
        with open(path, "xb") as output:
            output.write(canonical)
    except OSError:
        return jsonify({"error": "could not store profile image"}), 500

    existing = ProfileImage.query.filter_by(user_id=user.id).first()
    old_filename = existing.filename if existing else None

    if existing:
        existing.filename = filename
    else:
        db.session.add(ProfileImage(user_id=user.id, filename=filename))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        _unlink_profile_image(filename)
        raise

    if old_filename and old_filename != filename:
        _unlink_profile_image(old_filename)

    return jsonify(user.to_public()), 201


@app.delete("/api/profile/image")
def remove_profile_image():
    user, err = require_login()
    if err:
        return err

    image = ProfileImage.query.filter_by(user_id=user.id).first()

    if not image:
        return jsonify(user.to_public())

    filename = image.filename
    db.session.delete(image)
    db.session.commit()
    _unlink_profile_image(filename)

    return jsonify(user.to_public())


@app.get("/profile-images/<name>")
def serve_profile_image(name):
    viewer, err = require_login()
    if err:
        return err

    if not PROFILE_IMAGE_NAME_RE.fullmatch(name):
        abort(404)

    image = ProfileImage.query.filter_by(filename=name).first()
    if not image:
        abort(404)

    owner = db.session.get(User, image.user_id)
    if not owner:
        abort(404)

    if (
        not owner.profile_visible
        and viewer.id != owner.id
        and viewer.role != "admin"
    ):
        abort(404)

    response = send_from_directory(
        PROFILE_IMAGE_DIR,
        name,
        mimetype="image/jpeg",
        conditional=True,
    )
    response.cache_control.private = True
    response.cache_control.max_age = 86400
    return response


@app.post("/api/profile/cv-upload")
def cv_upload():
    """NLP-assisted profile building (brief §2.8): accepts raw CV text and
    extracts skills. Empty body still just marks the CV uploaded."""
    user, err = require_login()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    cv_text = data.get("cvText") or ""
    newly_found = [s for s in extract_skills(cv_text) if s.lower() not in user.skills.lower()]
    if newly_found:
        merged = [s for s in user.skills.split(",") if s] + newly_found
        user.skills = ",".join(merged)
    user.cv_uploaded = True
    recalc_completion(user)
    db.session.commit()
    return jsonify(user.to_public())


@app.patch("/api/profile/skills")
def update_skills():
    """Manual skill add/remove, independent of CV extraction."""
    user, err = require_login()
    if err:
        return err
    if user.role not in STUDENT_ROLES:
        return jsonify({"error": "skills apply to student and alumni accounts"}), 400
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    skill = (data.get("skill") or "").strip()
    if action not in ("add", "remove") or not skill:
        return jsonify({"error": "action ('add'/'remove') and skill are required"}), 400
    current = [s for s in user.skills.split(",") if s]
    if action == "add":
        if skill.lower() not in (c.lower() for c in current):
            current.append(skill)
    else:
        current = [c for c in current if c.lower() != skill.lower()]
    user.skills = ",".join(current)
    recalc_completion(user)
    db.session.commit()
    return jsonify(user.to_public())


@app.patch("/api/profile/portfolio")
def update_portfolio():
    """Editable profile fields. Students/alumni edit the portfolio block;
    business users edit the company profile block — role decides which
    keys are honoured."""
    user, err = require_login()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    student_fields = (("bio", "bio"), ("headline", "headline"), ("programme", "programme"),
                      ("year", "year"), ("campus", "campus"), ("github", "github_url"),
                      ("linkedin", "linkedin_url"), ("credly", "credly_url"),
                      ("website", "portfolio_url"))
    business_fields = (("bio", "bio"), ("headline", "headline"), ("industry", "industry"),
                       ("companyDescription", "company_desc"), ("location", "location"),
                       ("talentSought", "talent_sought"), ("website", "portfolio_url"))
    fields = student_fields if user.role in STUDENT_ROLES else (
        business_fields if user.role == "business" else (("bio", "bio"),))
    for key, attr in fields:
        if key in data:
            setattr(user, attr, (data.get(key) or "").strip())
    recalc_completion(user)
    db.session.commit()
    return jsonify(user.to_public())


@app.patch("/api/profile/visibility")
def update_visibility():
    user, err = require_login()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    for key, attr in (("profileVisible", "profile_visible"),
                      ("showEmail", "show_email"),
                      ("showSkills", "show_skills")):
        if key in data:
            setattr(user, attr, bool(data.get(key)))
    db.session.commit()
    return jsonify(user.to_public())


@app.get("/api/profile/export")
def export_profile():
    """POPIA s23 'right of access' — one JSON download containing
    everything the platform holds on the requesting user."""
    user, err = require_login()
    if err:
        return err
    payload = user.to_public()
    payload["raw"] = {
        "email": user.email, "headline": user.headline, "programme": user.programme,
        "year": user.year, "campus": user.campus, "industry": user.industry,
        "companyDescription": user.company_desc, "location": user.location,
        "talentSought": user.talent_sought,
        "createdAt": user.created_at.isoformat() if user.created_at else None,
    }
    payload["notifications"] = [n.to_dict() for n in
                                Notification.query.filter_by(user_id=user.id)
                                .order_by(Notification.id).all()]
    payload["coachHistory"] = [m.to_dict() for m in
                               CoachMessage.query.filter_by(user_id=user.id)
                               .order_by(CoachMessage.id).all()]
    payload["applications"] = [{"opportunityId": a.opportunity_id,
                                "at": a.created_at.isoformat()}
                               for a in Application.query.filter_by(user_id=user.id).all()]
    resp = jsonify(payload)
    resp.headers["Content-Disposition"] = 'attachment; filename="forge-my-data.json"'
    return resp


# ------------------------------------------------------------ onboarding --
@app.get("/api/onboarding")
def get_onboarding():
    user, err = require_login()
    if err:
        return err
    steps = ONBOARDING_STEPS.get(user.role, ["welcome"])
    return jsonify({"steps": steps, "step": user.onboarding_step,
                    "complete": user.onboarding_complete})


@app.post("/api/onboarding/advance")
def advance_onboarding():
    user, err = require_login()
    if err:
        return err
    steps = ONBOARDING_STEPS.get(user.role, ["welcome"])
    user.onboarding_step = min(user.onboarding_step + 1, len(steps) - 1)
    if user.onboarding_step >= len(steps) - 1:
        user.onboarding_complete = True
    db.session.commit()
    return jsonify({"steps": steps, "step": user.onboarding_step,
                    "complete": user.onboarding_complete})


@app.post("/api/onboarding/skip")
def skip_onboarding():
    user, err = require_login()
    if err:
        return err
    user.onboarding_complete = True
    db.session.commit()
    return jsonify({"steps": ONBOARDING_STEPS.get(user.role, ["welcome"]),
                    "step": user.onboarding_step, "complete": True})


# --------------------------------------------------------- notifications --
@app.get("/api/notifications")
def get_notifications():
    user, err = require_login()
    if err:
        return err
    notes = (Notification.query.filter_by(user_id=user.id)
             .order_by(Notification.id.desc()).limit(50).all())
    unread = Notification.query.filter_by(user_id=user.id, read=False).count()
    return jsonify({"notifications": [n.to_dict() for n in notes],
                    "unreadCount": unread})


@app.post("/api/notifications/<int:note_id>/read")
def mark_notification_read(note_id):
    user, err = require_login()
    if err:
        return err
    note = Notification.query.get_or_404(note_id)
    if note.user_id != user.id:
        return jsonify({"error": "not yours"}), 403
    note.read = True
    db.session.commit()
    return jsonify({"ok": True})


@app.post("/api/notifications/read-all")
def mark_all_notifications_read():
    user, err = require_login()
    if err:
        return err
    Notification.query.filter_by(user_id=user.id, read=False).update({"read": True})
    db.session.commit()
    return jsonify({"ok": True})


# -------------------------------------------------------- public profiles --
@app.get("/api/users/<int:user_id>")
def get_public_profile(user_id):
    viewer, err = require_login()
    if err:
        return err
    target = User.query.get_or_404(user_id)
    if not target.profile_visible and viewer.id != target.id and viewer.role != "admin":
        return jsonify({"error": "profile not visible"}), 404
    if viewer.id != target.id:
        db.session.add(ProfileView(viewed_user_id=target.id,
                                   viewer_user_id=viewer.id, source="profile"))
        db.session.commit()
        push_notification(target.id, "profile_view",
                          f"{viewer.name} viewed your profile")
    return jsonify(target.to_profile_view(viewer))


@app.post("/api/users/<int:user_id>/testimonials")
def add_testimonial(user_id):
    user, err = require_login()
    if err:
        return err
    target = User.query.get_or_404(user_id)
    text = (request.get_json(force=True) or {}).get("text", "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    if user.id == target.id:
        return jsonify({"error": "you can't leave yourself a testimonial"}), 400
    db.session.add(Testimonial(user_id=target.id, author_name=user.name,
                               author_role=user.role, text=text))
    db.session.commit()
    push_notification(target.id, "testimonial",
                      f"{user.name} left you a testimonial")
    return jsonify({"ok": True}), 201


# ---------------------------------------------------------- talent search --
@app.get("/api/search/candidates")
def search_candidates():
    """Business-side talent search. Matched skill terms are logged to
    SkillSearch, feeding the 'most searched skills' panel on student
    analytics dashboards (brief §2.7)."""
    user, err = require_login()
    if err:
        return err
    if user.role not in ("business", "admin"):
        return jsonify({"error": "business or admin only"}), 403
    terms = [t.strip().lower() for t in request.args.get("skills", "").split(",") if t.strip()]
    if not terms:
        return jsonify({"candidates": []})
    canonical = {s.lower(): s for s in SKILL_VOCAB}
    logged, results = set(), []
    targets = User.query.filter(User.role.in_(STUDENT_ROLES),
                                User.suspended.is_(False),
                                User.profile_visible.is_(True)).all()
    for target in targets:
        skills = [s.strip() for s in (target.skills or "").split(",") if s.strip()]
        lower = {s.lower() for s in skills}
        matched = [canonical.get(t, t) for t in terms if t in lower]
        if matched:
            logged.update(matched)
            results.append({"id": target.id, "name": target.name, "role": target.role,
                            "color": target.color, "programme": target.programme,
                            "completion": target.completion, "matchedSkills": matched})
    for skill in logged:
        db.session.add(SkillSearch(skill=skill, searcher_id=user.id))
    db.session.commit()
    results.sort(key=lambda r: -len(r["matchedSkills"]))
    return jsonify({"candidates": results})


# ------------------------------------------------------------- analytics --
@app.get("/api/analytics/student")
def student_analytics():
    user, err = require_login()
    if err:
        return err
    views = ProfileView.query.filter_by(viewed_user_id=user.id).all()
    accepted = NetworkRequest.query.filter_by(status="accepted") \
        .order_by(NetworkRequest.created_at).all()
    my_posts = Post.query.filter(Post.author_name == user.name,
                                 Post.removed.is_(False)).all()
    likes_received = sum(p.base_likes + Like.query.filter_by(post_id=p.id).count()
                         for p in my_posts)
    comments_received = sum(Comment.query.filter_by(post_id=p.id).count()
                            for p in my_posts)
    peers = User.query.filter(User.role == user.role,
                              User.programme == user.programme,
                              User.id != user.id).all()
    programme_avg = int(sum(p.completion for p in peers) / len(peers)) if peers else None
    mine = {s.strip().lower() for s in (user.skills or "").split(",") if s.strip()}
    counts = defaultdict(int)
    for search in SkillSearch.query.all():
        if search.skill.lower() in mine:
            counts[search.skill] += 1
    top = sorted(({"skill": k, "count": v} for k, v in counts.items()),
                 key=lambda x: -x["count"])[:5]
    return jsonify({
        "profileViews": {"total": len(views),
                         "series": daily_series([v.created_at for v in views])},
        "connections": {"total": len(accepted) + ConnectionNPC.query.count(),
                        "series": cumulative(daily_series([r.created_at for r in accepted]))},
        "engagement": {"posts": len(my_posts), "likes": likes_received,
                       "comments": comments_received},
        "peerComparison": {"me": user.completion, "programmeAvg": programme_avg,
                           "programme": user.programme},
        "topSearchedSkills": top,
    })


@app.get("/api/analytics/business")
def business_analytics():
    user, err = require_login()
    if err:
        return err
    if user.role not in ("business", "admin"):
        return jsonify({"error": "business or admin only"}), 403
    opps = Opportunity.query.filter_by(owner_user_id=user.id).all()
    pipeline, applicant_ids = [], []
    for opp in opps:
        apps = Application.query.filter_by(opportunity_id=opp.id).all()
        pipeline.append({"title": opp.title, "applicants": len(apps), "status": "live"})
        applicant_ids.extend(a.user_id for a in apps)
    applicants = [u for u in (User.query.get(i) for i in applicant_ids) if u]
    skill_counts, by_programme, by_year = defaultdict(int), defaultdict(int), defaultdict(int)
    for a in applicants:
        for s in (a.skills or "").split(","):
            if s.strip():
                skill_counts[s.strip()] += 1
        by_programme[a.programme or "Unspecified"] += 1
        by_year[a.year or "Unspecified"] += 1

    def dist(d):
        return sorted(({"label": k, "count": v} for k, v in d.items()),
                      key=lambda x: -x["count"])

    listings = BusinessListing.query.filter_by(owner_user_id=user.id).all()
    impressions = sum(l.impressions for l in listings)
    total_apps = len(applicant_ids)
    rate = f"{round(100 * total_apps / impressions)}%" if impressions else "—"
    return jsonify({
        "pipeline": pipeline,
        "engagement": {"impressions": impressions, "applications": total_apps, "rate": rate},
        "skillDistribution": dist(skill_counts),
        "demographics": {"byProgramme": dist(by_programme), "byYear": dist(by_year)},
        "reach": {"profileViews": ProfileView.query
                  .filter_by(viewed_user_id=user.id).count(),
                  "impressions": impressions},
    })


@app.get("/api/analytics/admin")
def admin_analytics():
    user, err = require_login()
    if err:
        return err
    if user.role != "admin":
        return jsonify({"error": "admin only"}), 403
    users = User.query.all()
    roles = defaultdict(int)
    for u in users:
        roles[u.role] += 1
    month_ago = datetime.utcnow() - timedelta(days=30)
    mau = sum(1 for u in users if u.last_seen and u.last_seen >= month_ago)
    pending = (ApprovalQueueItem.query.filter_by(status="pending").count()
               + AlumniVerification.query.filter_by(status="pending").count()
               + User.query.filter_by(role="business", business_approved=False).count())
    return jsonify({
        "usersByType": [
            {"label": "Students", "count": roles["trade"]},
            {"label": "Alumni", "count": roles["grad"]},
            {"label": "Businesses", "count": roles["business"]},
            {"label": "Admins", "count": roles["admin"]},
        ],
        "totals": {"users": len(users), "mau": mau,
                   "flagged": Post.query.filter_by(flagged=True, removed=False).count(),
                   "pendingApprovals": pending},
        "registrationSeries": daily_series([u.created_at for u in users]),
        "content": {
            "posts": Post.query.filter_by(removed=False).count(),
            "videos": Post.query.filter(Post.media.is_(True),
                                        Post.removed.is_(False)).count(),
            "opportunities": Opportunity.query.count(),
            "events": Event.query.count(),
        },
        "pipeline": {
            "listingQueue": ApprovalQueueItem.query.filter_by(status="pending").count(),
            "alumniQueue": AlumniVerification.query.filter_by(status="pending").count(),
            "businessVerifications":
                User.query.filter_by(role="business", business_approved=False).count(),
        },
    })


# -------------------------------------------------------- admin console --
def _admin_user_view(u):
    return {"id": u.id, "name": u.name, "username": u.username, "role": u.role,
            "email": u.email, "color": u.color, "suspended": u.suspended,
            "pendingBusiness": u.role == "business" and not u.business_approved,
            "alumniVerified": u.alumni_verified,
            "createdAt": u.created_at.isoformat() if u.created_at else None}


@app.get("/api/admin/users")
def admin_list_users():
    user, err = require_login()
    if err:
        return err
    if user.role != "admin":
        return jsonify({"error": "admin only"}), 403
    return jsonify([_admin_user_view(u) for u in
                    User.query.order_by(User.role, User.name).all()])


@app.post("/api/admin/users/<int:target_id>/<string:action>")
def admin_user_action(target_id, action):
    """approve-business | suspend | unsuspend | remove. 'remove' hard-deletes
    where possible and falls back to suspension when the account has linked
    activity that would break foreign keys."""
    user, err = require_login()
    if err:
        return err
    if user.role != "admin":
        return jsonify({"error": "admin only"}), 403
    if action not in ("approve-business", "suspend", "unsuspend", "remove"):
        return jsonify({"error": "unknown action"}), 400
    target = User.query.get_or_404(target_id)
    if target.role == "admin" and action in ("suspend", "remove"):
        return jsonify({"error": "admin accounts can't be actioned here"}), 400
    if action == "approve-business":
        if target.role != "business":
            return jsonify({"error": "not a business account"}), 400
        target.business_approved = True
        db.session.commit()
        push_notification(target.id, "approval",
                          "Your business account has been verified — you can post listings now.",
                          link="listings:listings")
        return jsonify({"ok": True, "note": f"{target.name} verified."})
    if action == "suspend":
        target.suspended = True
        db.session.commit()
        push_notification(target.id, "announcement",
                          "Your account has been suspended. Please contact the administrator.")
        return jsonify({"ok": True, "note": f"{target.name} suspended."})
    if action == "unsuspend":
        target.suspended = False
        db.session.commit()
        return jsonify({"ok": True, "note": f"{target.name} restored."})
    try:
        db.session.delete(target)
        db.session.commit()
        return jsonify({"ok": True, "note": f"{target.name} removed."})
    except Exception:
        db.session.rollback()
        fresh = User.query.get(target_id)
        if fresh:
            fresh.suspended = True
            db.session.commit()
            return jsonify({"ok": True,
                            "note": f"{target.name} has linked activity — suspended instead."})
        return jsonify({"ok": True, "note": "already removed."})


@app.post("/api/admin/announce")
def broadcast_announcement():
    """Platform-wide or role-targeted announcements — persisted
    notifications AND a live socket push."""
    user, err = require_login()
    if err:
        return err
    if user.role != "admin":
        return jsonify({"error": "admin only"}), 403
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    audience = data.get("audience") or "all"
    if not text:
        return jsonify({"error": "text required"}), 400
    if audience != "all" and audience not in ROLES:
        return jsonify({"error": "unknown audience"}), 400
    targets = (User.query.all() if audience == "all"
               else User.query.filter_by(role=audience).all())
    delivered = 0
    for target in targets:
        if not target.suspended:
            push_notification(target.id, "announcement", text)
            delivered += 1
    return jsonify({"ok": True, "delivered": delivered})


# ------------------------------------------------------------- frontend --
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "forge_demo.html")


@app.get("/manifest.webmanifest")
def manifest():
    return send_from_directory(app.static_folder, "manifest.webmanifest")


@app.get("/icons/<path:name>")
def icons(name):
    return send_from_directory(os.path.join(app.static_folder, "icons"), name)


# ----------------------------------------------------------------- seed --
def seed_demo_data(force=False):
    """Populate an empty database so the demo logins, dashboards, queues
    and moderation flows all have something to show."""
    if User.query.count() and not force:
        return False

    def days_ago(n, hour=10):
        return datetime.utcnow() - timedelta(days=n) - timedelta(hours=hour)

    def mk(username, name, role, **kw):
        u = User(username=username, password_hash=generate_password_hash("demo123"),
                 role=role, name=name, **kw)
        db.session.add(u)
        return u

    trade = mk("demo_trade", "Thabo Mokoena", "trade",
               email="thabo.mokoena@my.richfield.ac.za",
               programme="Diploma in Software Engineering", year="2nd year",
               campus="Durban Campus", headline="Aspiring full-stack developer",
               skills="Python,JavaScript,SQL,Flask,React",
               bio="Second-year software engineering student. I build small tools for my campus "
                   "society and document everything on GitHub.",
               github_url="https://github.com/thabo-m",
               linkedin_url="https://linkedin.com/in/thabo-m",
               completion=70, created_at=days_ago(11), last_seen=days_ago(0, 2))
    grad = mk("demo_grad", "Lerato Khumalo", "grad",
              email="lerato.khumalo@outlook.com",
              programme="BSc Information Technology", year="Class of 2021",
              campus="Durban Campus", headline="Data Analyst at KZN Logistics",
              skills="Python,SQL,data analysis,project management",
              bio="Richfield IT graduate, now analysing supply-chain data. Happy to mentor final-years.",
              linkedin_url="https://linkedin.com/in/lerato-k",
              credly_url="https://credly.com/users/lerato-k",
              alumni_verified=True, completion=80,
              created_at=days_ago(24), last_seen=days_ago(1, 4))
    biz = mk("demo_business", "Apex Manufacturing", "business",
             email="hire@apexmfg.co.za", headline="We hire makers and fixers",
             industry="Manufacturing", location="Durban, KZN",
             company_desc="Mid-size fabrication plant hiring welders, fitters and junior developers "
                          "for our digital workshop.",
             talent_sought="Welders, fitters, junior developers, data analysts",
             business_approved=True, completion=75,
             created_at=days_ago(21), last_seen=days_ago(0, 6))
    admin = mk("demo_admin", "Campus Administrator", "admin",
               email="administrator@richfield.ac.za", completion=100,
               created_at=days_ago(30), last_seen=days_ago(0, 1))
    pending_biz = mk("harbour_logistics", "Harbour Logistics", "business",
                     email="careers@harbourlog.co.za", industry="Logistics",
                     location="Durban Harbour", headline="Port operations careers",
                     completion=40, created_at=days_ago(4), last_seen=days_ago(2, 3))
    pending_alum = mk("sipho", "Sipho Ngcobo", "grad",
                      email="sipho.ngcobo@outlook.com",
                      programme="Diploma in Software Engineering", year="Class of 2023",
                      skills="JavaScript,React,customer service", completion=50,
                      created_at=days_ago(6), last_seen=days_ago(3, 5))

    peers = [
        ("nikiwe", "Nikiwe Dlamini", "Diploma in Software Engineering",
         "Python,SQL,Figma,UX design", 90, 13),
        ("jaco", "Jaco van Wyk", "Diploma in Software Engineering",
         "JavaScript,React,Flask", 70, 9),
        ("zanle", "Zanele Ndlovu", "Diploma in Software Engineering",
         "Python,data analysis", 60, 7),
        ("kabelo", "Kabelo Sithole", "Diploma in Electrical Engineering",
         "PLC programming,electrical wiring,HVAC installation", 75, 16),
        ("amara", "Amara Okoro", "BSc Information Technology",
         "SQL,data analysis,project management", 85, 5),
        ("pieter", "Pieter Botha", "Certificate in Welding Technology",
         "MIG welding,TIG welding,blueprint reading,pipe fitting", 65, 19),
    ]
    peer_users = {}
    for username, name, programme, skills, completion, created in peers:
        peer_users[username] = mk(
            username, name, "trade", email=f"{username}@my.richfield.ac.za",
            programme=programme, year="2nd year", skills=skills,
            completion=completion, created_at=days_ago(created),
            last_seen=days_ago(created % 6, 3))

    db.session.flush()  # assign ids before creating dependent rows

    # ---- posts ----
    def post(feed, name, role, color, body, likes, flagged=False, pick=False, media=False):
        p = Post(feed=feed, author_name=name, author_role=role, color=color,
                 body=body, base_likes=likes, flagged=flagged, pick=pick, media=media)
        db.session.add(p)
        return p

    p1 = post("trade", "Nikiwe Dlamini", "trade", "#2c6e62",
              "Shipped my first full-stack project — a campus room-booking app in Flask + React. "
              "Repo's in my profile, feedback welcome!", 12)
    post("trade", "Thabo Mokoena", "trade", "#b5432b",
         "Site visit to Apex Manufacturing today. Nothing beats seeing PLC panels wired live — "
         "video from the floor coming later this week.", 8)
    post("trade", "Pieter Botha", "trade", "#a5721c",
         "6G pipe welds from today's workshop. My TIG hand finally stopped shaking on the cap pass.",
         15, media=True)
    post("trade", "Zanele Ndlovu", "trade", "#2c6e62",
         "Reminder: Career Services runs a CV clinic on Friday. Bring a printed copy and your "
         "GitHub login.", 5)
    post("trade", "Unknown account", "trade", "#3b3128",
         "DM me your login details for a guaranteed internship placement!!!", 0, flagged=True)
    post("grad", "Lerato Khumalo", "grad", "#a5721c",
         "Three years from Richfield graduate to analytics team lead. If you're final-year and "
         "wondering whether the data route pays off — ask me anything.", 22, pick=True)
    post("grad", "Mentor Circle", "grad", "#2c6e62",
         "The monthly alumni mentoring circle moves to the first Thursday. Current students welcome.", 9)
    post("business", "Apex Manufacturing", "business", "#b5432b",
         "Our graduate intake opens next month — welders, fitters and one junior dev. "
         "Watch the Discover tab.", 6)
    post("business", "Studio Moyo", "business", "#a5721c",
         "Hiring a UX design learner to shadow our product team. A portfolio link beats a CV "
         "every time.", 4)
    post("admin", "Richfield Careers Office", "admin", "#1e4f46",
         "Welcome to Forge — the official Richfield professional network. Complete your profile "
         "to appear in business searches.", 30, pick=True)

    db.session.flush()  # assign post ids before creating dependent comments

    db.session.add(Comment(post_id=p1.id, author_name="Jaco van Wyk",
                           text="Clean routing — did you split it into Blueprints?"))
    db.session.add(Comment(post_id=p1.id, author_name="Lerato Khumalo",
                           text="Nice. Add a README with setup steps and recruiters will actually run it."))

    # ---- opportunities ----
    def opp(title, co, tags, owner=None):
        o = Opportunity(title=title, co=co, tags=tags, match=60, owner_user_id=owner)
        db.session.add(o)
        return o

    opp_weld = opp("Welder — Fabrication Team", "Apex Manufacturing",
                   "MIG welding,TIG welding,blueprint reading", owner=biz.id)
    opp_fab = opp("Fabrication Apprentice", "Apex Manufacturing",
                  "pipe fitting,blueprint reading", owner=biz.id)
    opp("Junior Developer (Graduate Programme)", "Cape Digital Labs", "Python,JavaScript,SQL,React")
    opp("Data Analyst Internship", "KZN Logistics", "Python,SQL,data analysis")
    opp("Electrical Apprentice", "BrightVolt Energy", "electrical wiring,PLC programming")
    opp("UX Design Learnership", "Studio Moyo", "Figma,UX design")
    opp("IT Support Learnership", "Richfield IT Services", "customer service,SQL")

    # ---- events & pathways ----
    db.session.add(Event(title="Career Fair 2026", place="Durban Campus Atrium", day="14", mon="Mar"))
    db.session.add(Event(title="CV & LinkedIn Clinic", place="Online — Teams", day="21", mon="Mar"))
    db.session.add(Event(title="Alumni Networking Evening", place="Sandton Campus", day="9", mon="Apr"))
    db.session.add(Pathway(prog="Diploma in Software Engineering",
                           rows="Junior Developer — Cape Digital Labs|Full-stack Developer — Freewave "
                                "Studio|Team Lead — Richfield Alumni Ventures"))
    db.session.add(Pathway(prog="BSc Information Technology",
                           rows="IT Intern — KZN Logistics|Data Analyst — KZN Logistics|"
                                "Analytics Manager — RetailCo"))
    db.session.add(Pathway(prog="Certificate in Welding Technology",
                           rows="Apprentice Welder — Apex Manufacturing|Certified Welder — Durban "
                                "Shipyards|Workshop Foreman — Apex Manufacturing"))

    # ---- network ----
    db.session.add(NetworkRequest(name="Naledi Mokoena", role="Alumni · BSc IT 2019",
                                  color="#b5432b", status="pending", created_at=days_ago(2)))
    db.session.add(NetworkRequest(name="Mr Dube (Lecturer)", role="Lecturer · Software Engineering",
                                  color="#a5721c", status="pending", created_at=days_ago(1)))
    for name, role, created in (("Ayesha Patel", "Alumni · Class of 2020", 13),
                                ("Sibusiso Mthembu", "Senior Welder", 9),
                                ("Karen Levy", "Technical Recruiter", 5)):
        db.session.add(NetworkRequest(name=name, role=role, color="#2c6e62",
                                      status="accepted", created_at=days_ago(created)))
    for name, role in (("Priya Naidoo", "Alumni · Data Engineer"),
                       ("Mandla Zulu", "Final-year · Electrical"),
                       ("Refilwe Maseko", "Campus Ambassador")):
        db.session.add(Suggested(name=name, role=role, color="#b5432b"))
    for name, role, skill, endo in (("Ayesha Patel", "Alumni · Class of 2020", "Python", 4),
                                    ("Sibusiso Mthembu", "Senior Welder", "TIG welding", 7),
                                    ("Karen Levy", "Technical Recruiter", "candidate screening", 2)):
        db.session.add(ConnectionNPC(name=name, role=role, color="#a5721c",
                                     skill=skill, endorsements=endo))

    # ---- conversations ----
    c1 = Conversation(slug="ayesha", name="Ayesha Patel", color="#b5432b", unread=True)
    db.session.add(c1); db.session.flush()
    for who, text in (("them", "Hi Thabo — saw the booking app on the feed. Nice work!"),
                      ("me", "Thanks Ayesha! Still fighting with the deployment story."),
                      ("them", "Deploy it and add the link to your portfolio — that's what "
                               "recruiters check first.")):
        db.session.add(Message(conversation_id=c1.id, who=who, text=text))
    c2 = Conversation(slug="apex", name="Apex Manufacturing · HR", color="#a5721c", unread=False)
    db.session.add(c2); db.session.flush()
    for who, text in (("them", "Morning Thabo — we shortlist for the site-visit programme next "
                               "week. Keep your CV current."),
                      ("me", "Will do — uploaded the latest version yesterday.")):
        db.session.add(Message(conversation_id=c2.id, who=who, text=text))

    # ---- pending approvals for the admin demo ----
    db.session.add(AlumniVerification(user_id=pending_alum.id,
                                      document_ref="richfield-diploma-sipho-2023.pdf",
                                      note="Scanned diploma + certified ID copy", status="pending"))
    queue = ApprovalQueueItem(title="Weekend Warehouse Assistants", co="Harbour Logistics",
                              tags="customer service,project management", status="pending")
    db.session.add(queue); db.session.flush()
    db.session.add(BusinessListing(owner_user_id=pending_biz.id, queue_item_id=queue.id,
                                   title=queue.title, co=queue.co, tags=queue.tags, status="pending"))
    apex_queue = ApprovalQueueItem(title=opp_weld.title, co="Apex Manufacturing",
                                   tags=opp_weld.tags, status="approved", decided_at=days_ago(8))
    db.session.add(apex_queue); db.session.flush()
    apex_listing = BusinessListing(owner_user_id=biz.id, queue_item_id=apex_queue.id,
                                   title=opp_weld.title, co="Apex Manufacturing",
                                   tags=opp_weld.tags, status="live", impressions=34)
    db.session.add(apex_listing); db.session.flush()
    opp_weld.listing_id = apex_listing.id

    # ---- analytics seed data ----
    for i, count in enumerate([1, 0, 2, 1, 0, 3, 2, 1, 4, 2, 3, 5, 4, 6]):
        for _ in range(count):
            db.session.add(ProfileView(viewed_user_id=trade.id, viewer_user_id=biz.id,
                                       source="search", created_at=days_ago(13 - i, 7)))
    for _ in range(4):
        db.session.add(ProfileView(viewed_user_id=biz.id, viewer_user_id=trade.id,
                                   source="profile", created_at=days_ago(3, 6)))
    for skill, count, created in (("Python", 9, 3), ("SQL", 6, 4), ("MIG welding", 4, 6),
                                  ("React", 3, 2), ("data analysis", 5, 5), ("PLC programming", 2, 8)):
        for _ in range(count):
            db.session.add(SkillSearch(skill=skill, searcher_id=biz.id, created_at=days_ago(created)))
    by_name = {u.username: u for u in (trade, grad, biz, admin, pending_biz, pending_alum)}
    by_name.update(peer_users)
    for username, opportunity, created in (("pieter", opp_weld, 6), ("kabelo", opp_fab, 4),
                                           ("nikiwe", opp_weld, 3), ("amara", opp_fab, 2)):
        db.session.add(Application(opportunity_id=opportunity.id,
                                   user_id=by_name[username].id, created_at=days_ago(created)))

    db.session.commit()
    for u in (trade, grad, biz, admin, pending_biz, pending_alum):
        seed_coach_intro(u)
    return True


@app.cli.command("seed-demo")
def seed_demo_command():
    """Seed local demo identities only when explicit demo mode is active."""
    if not app.config.get("FORGE_DEMO_MODE", False):
        raise ClickException(
            "seed-demo is disabled; set FORGE_ENV=development and "
            "FORGE_DEMO_MODE=1 explicitly."
        )
    print("Seeded." if seed_demo_data() else "Database not empty — skipped.")


if __name__ == "__main__":
    debug = bool(app.config.get("DEBUG", False))
    demo_mode = bool(app.config.get("FORGE_DEMO_MODE", False))

    with app.app_context():
        db.create_all()
        # Demo identities are never created implicitly in a normal startup.
        # When explicitly enabled, avoid double seeding under the debug reloader.
        should_seed_demo = demo_mode and (
            (not debug) or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
        )
        if should_seed_demo and seed_demo_data():
            print("=" * 66)
            print("Seeded local demo data. Demo logins (password 'demo123'):")
            print("  demo_trade · demo_grad · demo_business · demo_admin")
            print("Upgraded from an older schema? Delete instance/forge.db")
            print("and restart to re-seed with the new columns.")
            print("=" * 66)

    socketio.run(app, host="0.0.0.0",
                 port=int(os.environ.get("PORT", 5000)), debug=debug)

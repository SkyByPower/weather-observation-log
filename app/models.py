import secrets
from datetime import datetime

from flask import url_for
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, login_manager

ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLES = (ROLE_ADMIN, ROLE_USER)

# Көп–көп байланыс: станция қандай параметрлерді өлшейді
station_parameters = db.Table(
    "station_parameters",
    db.Column("station_id", db.Integer, db.ForeignKey("stations.id", ondelete="CASCADE"), primary_key=True),
    db.Column("parameter_id", db.Integer, db.ForeignKey("parameters.id", ondelete="CASCADE"), primary_key=True),
)


def generate_token():
    return secrets.token_hex(20)


def upload_url(path):
    return url_for("static", filename=f"uploads/{path}", _external=True) if path else None


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(10), nullable=False, default=ROLE_USER)
    api_token = db.Column(db.String(64), unique=True, default=generate_token)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    observations = db.relationship("Observation", back_populates="author", lazy="dynamic")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == ROLE_ADMIN

    def __repr__(self):
        return f"<User {self.username}>"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Station(db.Model):
    __tablename__ = "stations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    city = db.Column(db.String(100), nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    elevation = db.Column(db.Float)
    phone = db.Column(db.String(30))
    email = db.Column(db.String(120))
    description = db.Column(db.Text)
    photo = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    observations = db.relationship(
        "Observation",
        back_populates="station",
        lazy="dynamic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    parameters = db.relationship(
        "Parameter", secondary=station_parameters, back_populates="stations", order_by="Parameter.name"
    )

    def to_dict(self, with_parameters=False):
        data = {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "city": self.city,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "elevation": self.elevation,
            "phone": self.phone,
            "email": self.email,
            "description": self.description,
            "is_active": self.is_active,
            "photo_url": upload_url(self.photo),
            "observations_count": self.observations.count(),
        }
        if with_parameters:
            data["parameters"] = [p.to_dict() for p in self.parameters]
        return data

    def __repr__(self):
        return f"<Station {self.code}>"


class Parameter(db.Model):
    __tablename__ = "parameters"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), unique=True, nullable=False)
    code = db.Column(db.String(30), unique=True, nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    min_value = db.Column(db.Float, nullable=False)
    max_value = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(500))

    observations = db.relationship("Observation", back_populates="parameter", lazy="dynamic")
    stations = db.relationship("Station", secondary=station_parameters, back_populates="parameters")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "unit": self.unit,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "description": self.description,
        }

    def __repr__(self):
        return f"<Parameter {self.code}>"


class Observation(db.Model):
    __tablename__ = "observations"

    id = db.Column(db.Integer, primary_key=True)
    station_id = db.Column(db.Integer, db.ForeignKey("stations.id", ondelete="CASCADE"), nullable=False, index=True)
    parameter_id = db.Column(db.Integer, db.ForeignKey("parameters.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    value = db.Column(db.Float, nullable=False)
    observed_at = db.Column(db.DateTime, nullable=False, index=True)
    note = db.Column(db.String(500))
    attachment = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    station = db.relationship("Station", back_populates="observations")
    parameter = db.relationship("Parameter", back_populates="observations")
    author = db.relationship("User", back_populates="observations")

    def can_edit(self, user):
        return user.is_authenticated and (user.is_admin or user.id == self.user_id)

    def to_dict(self):
        return {
            "id": self.id,
            "station": {"id": self.station.id, "name": self.station.name, "code": self.station.code},
            "parameter": {
                "id": self.parameter.id,
                "code": self.parameter.code,
                "name": self.parameter.name,
                "unit": self.parameter.unit,
            },
            "value": self.value,
            "observed_at": self.observed_at.isoformat(timespec="minutes"),
            "note": self.note,
            "attachment_url": upload_url(self.attachment),
            "author": self.author.username if self.author else None,
            "created_at": self.created_at.isoformat(timespec="seconds"),
        }

    def __repr__(self):
        return f"<Observation {self.id} {self.value}>"

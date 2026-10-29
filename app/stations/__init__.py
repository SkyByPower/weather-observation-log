from flask import Blueprint

bp = Blueprint("stations", __name__, url_prefix="/stations")

from . import routes  # noqa: E402,F401

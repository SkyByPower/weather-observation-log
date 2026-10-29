from flask import Blueprint

bp = Blueprint("observations", __name__, url_prefix="/observations")

from . import routes  # noqa: E402,F401

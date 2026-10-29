import os
import sqlite3

from flask import Flask, jsonify, render_template, request, url_for
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

from .i18n import LANGUAGES, get_locale, gettext, lazy_gettext as _l, translate_data

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

ERROR_MESSAGES = {
    400: _l("Қате сұраныс"),
    403: _l("Қолжетімділік жоқ"),
    404: _l("Бет табылмады"),
    405: _l("Бұл әдіске рұқсат жоқ"),
    413: _l("Файл тым үлкен"),
    500: _l("Сервердің ішкі қатесі"),
}


@event.listens_for(Engine, "connect")
def _configure_sqlite(dbapi_connection, _record):
    """SQLite: сыртқы кілттерді қосу және кириллицамен жұмыс істейтін lower()."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.create_function(
            "lower", 1, lambda s: s.lower() if isinstance(s, str) else s, deterministic=True
        )
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_app(config_class="config.Config"):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    # JSON-да қазақша мәтін \uXXXX емес, оқылатын күйде шықсын
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    os.makedirs(app.instance_path, exist_ok=True)
    for sub in ("stations", "observations"):
        os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], sub), exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = _l("Бұл бетті ашу үшін жүйеге кіріңіз.")
    login_manager.localize_callback = gettext
    login_manager.login_message_category = "warning"

    from .admin import bp as admin_bp
    from .api import bp as api_bp
    from .auth import bp as auth_bp
    from .main import bp as main_bp
    from .observations import bp as observations_bp
    from .stations import bp as stations_bp

    for blueprint in (main_bp, auth_bp, stations_bp, observations_bp, admin_bp, api_bp):
        app.register_blueprint(blueprint)
    # API кілт арқылы аутентификацияланады, сондықтан CSRF токені қажет емес
    csrf.exempt(api_bp)

    register_error_handlers(app)
    register_template_helpers(app)

    from .commands import register_commands

    register_commands(app)
    return app


def register_error_handlers(app):
    def render_error(code):
        if code == 500:
            db.session.rollback()
        if request.path.startswith("/api/"):
            return jsonify(error=str(ERROR_MESSAGES[code]), status=code), code
        template = f"errors/{code}.html" if code in (404, 500) else "errors/generic.html"
        return render_template(template, code=code, message=str(ERROR_MESSAGES[code])), code

    for code in ERROR_MESSAGES:
        app.register_error_handler(code, lambda _e, c=code: render_error(c))


def register_template_helpers(app):
    app.jinja_env.globals.update(_=gettext, get_locale=get_locale, LANGUAGES=LANGUAGES)
    app.jinja_env.filters["tr"] = translate_data

    @app.template_global()
    def url_with_args(**updates):
        """Ағымдағы URL-ді сақтап, тек көрсетілген параметрлерді (мыс. page) ауыстырады."""
        params = dict(request.view_args or {})
        params.update(request.args.to_dict())
        params.update(updates)
        params = {k: v for k, v in params.items() if v not in (None, "")}
        return url_for(request.endpoint, **params)

    @app.template_filter("dt")
    def format_datetime(value, fmt="%d.%m.%Y %H:%M"):
        return value.strftime(fmt) if value else "—"

    @app.template_filter("num")
    def format_number(value, digits=1):
        if value is None:
            return "—"
        return f"{value:.{digits}f}"

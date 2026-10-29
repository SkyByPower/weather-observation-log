from urllib.parse import urlsplit

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func

from .. import db
from ..forms import LoginForm, RegisterForm
from ..models import Observation, User, generate_token
from . import bp


def _safe_next(target):
    """Тек өз сайтымыздағы салыстырмалы адреске қайта бағыттаймыз (open redirect-тен қорғау)."""
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return None
    return target if not urlsplit(target).netloc else None


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(username=form.username.data.strip(), email=form.email.data.strip().lower())
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("Тіркелу сәтті өтті! Енді жүйеге кіріңіз.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter(func.lower(User.username) == form.username.data.strip().lower()).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            flash(f"Қош келдіңіз, {user.username}!", "success")
            return redirect(_safe_next(request.args.get("next")) or url_for("main.index"))
        flash("Пайдаланушы аты немесе құпиясөз қате.", "danger")
    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Сіз жүйеден шықтыңыз.", "info")
    return redirect(url_for("main.index"))


@bp.route("/profile")
@login_required
def profile():
    recent = (
        current_user.observations.order_by(Observation.observed_at.desc()).limit(10).all()
    )
    return render_template(
        "auth/profile.html", recent=recent, total=current_user.observations.count()
    )


@bp.route("/profile/token", methods=["POST"])
@login_required
def regenerate_token():
    current_user.api_token = generate_token()
    db.session.commit()
    flash("Жаңа API кілті жасалды. Ескі кілт енді жарамсыз.", "success")
    return redirect(url_for("auth.profile"))

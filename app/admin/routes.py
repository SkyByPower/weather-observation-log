from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_

from .. import db
from ..forms import ParameterForm
from ..i18n import gettext as _
from ..models import ROLES, Observation, Parameter, User
from ..utils import admin_required
from . import bp


@bp.route("/")
@admin_required
def index():
    return redirect(url_for("admin.users"))


# ---------- Пайдаланушылар ----------

@bp.route("/users")
@admin_required
def users():
    q = request.args.get("q", "").strip()
    role = request.args.get("role", "")
    query = User.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.username.ilike(like), User.email.ilike(like)))
    if role in ROLES:
        query = query.filter(User.role == role)
    pagination = query.order_by(User.created_at.desc(), User.id.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=current_app.config["USERS_PER_PAGE"], error_out=False
    )
    counts = dict(
        db.session.query(Observation.user_id, func.count(Observation.id)).group_by(Observation.user_id).all()
    )
    return render_template(
        "admin/users.html", pagination=pagination, counts=counts, roles=ROLES, filters={"q": q, "role": role}
    )


@bp.route("/users/<int:user_id>/role", methods=["POST"])
@admin_required
def change_role(user_id):
    user = db.get_or_404(User, user_id)
    role = request.form.get("role")
    if role not in ROLES:
        flash(_("Белгісіз рөл."), "danger")
    elif user.id == current_user.id:
        flash(_("Өз рөліңізді өзгерте алмайсыз."), "warning")
    else:
        user.role = role
        db.session.commit()
        flash(_("{user} рөлі «{role}» болып өзгертілді.", user=user.username, role=role), "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash(_("Өз аккаунтыңызды өшіре алмайсыз."), "warning")
        return redirect(url_for("admin.users"))
    # Бақылаулар сақталады, тек авторы бос қалады
    Observation.query.filter_by(user_id=user.id).update({"user_id": None})
    db.session.delete(user)
    db.session.commit()
    flash(_("{user} пайдаланушысы өшірілді.", user=user.username), "info")
    return redirect(url_for("admin.users"))


# ---------- Параметрлер ----------

@bp.route("/parameters")
@admin_required
def parameters():
    counts = dict(
        db.session.query(Observation.parameter_id, func.count(Observation.id)).group_by(Observation.parameter_id).all()
    )
    return render_template(
        "admin/parameters.html", parameters=Parameter.query.order_by(Parameter.name).all(), counts=counts
    )


def _fill_parameter(parameter, form):
    parameter.name = form.name.data.strip()
    parameter.code = form.code.data.strip()
    parameter.unit = form.unit.data.strip()
    parameter.min_value = form.min_value.data
    parameter.max_value = form.max_value.data
    parameter.description = (form.description.data or "").strip() or None


@bp.route("/parameters/new", methods=["GET", "POST"])
@admin_required
def create_parameter():
    form = ParameterForm()
    if form.validate_on_submit():
        parameter = Parameter()
        _fill_parameter(parameter, form)
        db.session.add(parameter)
        db.session.commit()
        flash(_("«{name}» параметрі қосылды.", name=parameter.name), "success")
        return redirect(url_for("admin.parameters"))
    return render_template("admin/parameter_form.html", form=form, parameter=None)


@bp.route("/parameters/<int:parameter_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_parameter(parameter_id):
    parameter = db.get_or_404(Parameter, parameter_id)
    form = ParameterForm(obj=parameter, parameter=parameter)
    if form.validate_on_submit():
        _fill_parameter(parameter, form)
        db.session.commit()
        flash(_("Параметр жаңартылды."), "success")
        return redirect(url_for("admin.parameters"))
    return render_template("admin/parameter_form.html", form=form, parameter=parameter)


@bp.route("/parameters/<int:parameter_id>/delete", methods=["POST"])
@admin_required
def delete_parameter(parameter_id):
    parameter = db.get_or_404(Parameter, parameter_id)
    used = parameter.observations.count()
    if used:
        flash(_("«{name}» параметрін өшіру мүмкін емес: оған {count} бақылау тіркелген.", name=parameter.name, count=used), "danger")
    else:
        db.session.delete(parameter)
        db.session.commit()
        flash(_("«{name}» параметрі өшірілді.", name=parameter.name), "info")
    return redirect(url_for("admin.parameters"))

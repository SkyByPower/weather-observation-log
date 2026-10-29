from datetime import datetime

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from .. import db
from ..forms import ObservationForm
from ..models import Observation, Parameter, Station
from ..services import apply_date_filter, parse_date
from ..utils import DOCUMENT_EXTENSIONS, delete_upload, has_file, save_upload
from . import bp

SORTS = {
    "date_desc": ((Observation.observed_at.desc(),), "Күні: жаңадан ескіге"),
    "date_asc": ((Observation.observed_at.asc(),), "Күні: ескіден жаңаға"),
    "value_desc": ((Observation.value.desc(),), "Мәні: үлкеннен кішіге"),
    "value_asc": ((Observation.value.asc(),), "Мәні: кішіден үлкенге"),
    "station": ((Station.name.asc(), Observation.observed_at.desc()), "Станция атауы"),
}


def _filtered_query(args):
    query = Observation.query.join(Observation.station).join(Observation.parameter)
    filters = {
        "q": args.get("q", "").strip(),
        "station_id": args.get("station_id", type=int),
        "parameter_id": args.get("parameter_id", type=int),
        "date_from": parse_date(args.get("date_from")),
        "date_to": parse_date(args.get("date_to")),
        "mine": args.get("mine") == "1" and current_user.is_authenticated,
        "sort": args.get("sort") if args.get("sort") in SORTS else "date_desc",
    }
    if filters["q"]:
        like = f"%{filters['q']}%"
        query = query.filter(
            or_(Observation.note.ilike(like), Station.name.ilike(like), Station.code.ilike(like), Parameter.name.ilike(like))
        )
    if filters["station_id"]:
        query = query.filter(Observation.station_id == filters["station_id"])
    if filters["parameter_id"]:
        query = query.filter(Observation.parameter_id == filters["parameter_id"])
    if filters["mine"]:
        query = query.filter(Observation.user_id == current_user.id)
    query = apply_date_filter(query, filters["date_from"], filters["date_to"])
    return query, filters


@bp.route("/")
def list_observations():
    query, filters = _filtered_query(request.args)

    # Бір параметр таңдалса — сүзілген деректердің орташа мәнін көрсетеміз
    summary = None
    if filters["parameter_id"]:
        avg, vmin, vmax, count = query.with_entities(
            func.avg(Observation.value), func.min(Observation.value), func.max(Observation.value), func.count(Observation.id)
        ).one()
        summary = {
            "parameter": db.session.get(Parameter, filters["parameter_id"]),
            "avg": avg, "min": vmin, "max": vmax, "count": count,
        }

    page = request.args.get("page", 1, type=int)
    pagination = query.order_by(*SORTS[filters["sort"]][0], Observation.id.desc()).paginate(
        page=page, per_page=current_app.config["OBSERVATIONS_PER_PAGE"], error_out=False
    )
    return render_template(
        "observations/list.html",
        pagination=pagination,
        filters=filters,
        summary=summary,
        sorts=SORTS,
        stations=Station.query.order_by(Station.name).all(),
        parameters=Parameter.query.order_by(Parameter.name).all(),
    )


@bp.route("/<int:observation_id>")
def detail(observation_id):
    observation = db.get_or_404(Observation, observation_id)
    return render_template("observations/detail.html", obs=observation)


def _fill_observation(observation, form):
    observation.station_id = form.station_id.data
    observation.parameter_id = form.parameter_id.data
    observation.value = form.value.data
    observation.observed_at = form.observed_at.data
    observation.note = (form.note.data or "").strip() or None


def _save_attachment(observation, form):
    if not has_file(form.attachment_file.data):
        return True
    try:
        new_file = save_upload(form.attachment_file.data, "observations", DOCUMENT_EXTENSIONS)
    except ValueError as exc:
        form.attachment_file.errors.append(str(exc))
        return False
    delete_upload(observation.attachment)
    observation.attachment = new_file
    return True


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    form = ObservationForm()
    if request.method == "GET":
        form.observed_at.data = datetime.now().replace(second=0, microsecond=0)
        preset = request.args.get("station_id", type=int)
        if preset:
            form.station_id.data = preset
    if form.validate_on_submit():
        observation = Observation(user_id=current_user.id)
        _fill_observation(observation, form)
        if _save_attachment(observation, form):
            db.session.add(observation)
            db.session.commit()
            flash("Бақылау жазбасы қосылды.", "success")
            return redirect(url_for("observations.detail", observation_id=observation.id))
    return render_template("observations/form.html", form=form, obs=None)


@bp.route("/<int:observation_id>/edit", methods=["GET", "POST"])
@login_required
def edit(observation_id):
    observation = db.get_or_404(Observation, observation_id)
    if not observation.can_edit(current_user):
        abort(403)
    form = ObservationForm(obj=observation)
    if form.validate_on_submit():
        _fill_observation(observation, form)
        if _save_attachment(observation, form):
            db.session.commit()
            flash("Бақылау жазбасы жаңартылды.", "success")
            return redirect(url_for("observations.detail", observation_id=observation.id))
        db.session.rollback()
    return render_template("observations/form.html", form=form, obs=observation)


@bp.route("/<int:observation_id>/delete", methods=["POST"])
@login_required
def delete(observation_id):
    observation = db.get_or_404(Observation, observation_id)
    if not observation.can_edit(current_user):
        abort(403)
    attachment = observation.attachment
    db.session.delete(observation)
    db.session.commit()
    delete_upload(attachment)
    flash("Бақылау жазбасы өшірілді.", "info")
    return redirect(url_for("observations.list_observations"))

from datetime import date, timedelta

from flask import current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import func, or_

from .. import db
from ..forms import StationForm
from ..models import Observation, Parameter, Station
from ..services import latest_conditions, parameter_averages
from ..utils import IMAGE_EXTENSIONS, admin_required, delete_upload, has_file, save_upload
from . import bp

SORTS = {
    "name": (Station.name.asc(), "Атауы (А–Я)"),
    "-name": (Station.name.desc(), "Атауы (Я–А)"),
    "city": (Station.city.asc(), "Қала бойынша"),
    "-elevation": (Station.elevation.desc(), "Биіктігі (жоғарыдан)"),
    "newest": (Station.created_at.desc(), "Жаңалары алдымен"),
}


@bp.route("/")
def list_stations():
    q = request.args.get("q", "").strip()
    city = request.args.get("city", "").strip()
    status = request.args.get("status", "")
    sort = request.args.get("sort", "name")
    page = request.args.get("page", 1, type=int)

    query = Station.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Station.name.ilike(like), Station.code.ilike(like), Station.city.ilike(like)))
    if city:
        query = query.filter(Station.city == city)
    if status in ("active", "inactive"):
        query = query.filter(Station.is_active.is_(status == "active"))

    order = SORTS.get(sort, SORTS["name"])[0]
    pagination = query.order_by(order, Station.id).paginate(
        page=page, per_page=current_app.config["STATIONS_PER_PAGE"], error_out=False
    )
    counts = dict(
        db.session.query(Observation.station_id, func.count(Observation.id)).group_by(Observation.station_id).all()
    )
    cities = [c for (c,) in db.session.query(Station.city).distinct().order_by(Station.city)]
    return render_template(
        "stations/list.html",
        pagination=pagination,
        counts=counts,
        cities=cities,
        conditions=latest_conditions(),
        sorts=SORTS,
        filters={"q": q, "city": city, "status": status, "sort": sort},
    )


@bp.route("/<int:station_id>")
def detail(station_id):
    station = db.get_or_404(Station, station_id)
    today = date.today()
    latest = station.observations.order_by(Observation.observed_at.desc()).limit(10).all()
    averages = parameter_averages(station.id, today - timedelta(days=6), today)
    return render_template(
        "stations/detail.html",
        station=station,
        latest=latest,
        averages=averages,
        condition=latest_conditions().get(station.id),
        total=station.observations.count(),
    )


def _fill_station(station, form):
    station.name = form.name.data.strip()
    station.code = form.code.data.strip()
    station.city = form.city.data.strip()
    station.latitude = form.latitude.data
    station.longitude = form.longitude.data
    station.elevation = form.elevation.data
    station.phone = (form.phone.data or "").strip() or None
    station.email = (form.email.data or "").strip().lower() or None
    station.description = (form.description.data or "").strip() or None
    station.is_active = form.is_active.data
    station.parameters = Parameter.query.filter(Parameter.id.in_(form.parameter_ids.data or [])).all()


def _save_photo(station, form):
    """Жаңа фото жүктелсе — сақтайды. Қате болса форма өрісіне жазып, False қайтарады."""
    if not has_file(form.photo_file.data):
        return True
    try:
        new_photo = save_upload(form.photo_file.data, "stations", IMAGE_EXTENSIONS)
    except ValueError as exc:
        form.photo_file.errors.append(str(exc))
        return False
    delete_upload(station.photo)
    station.photo = new_photo
    return True


@bp.route("/new", methods=["GET", "POST"])
@admin_required
def create():
    form = StationForm()
    if request.method == "GET":
        form.parameter_ids.data = [p.id for p in Parameter.query.all()]
    if form.validate_on_submit():
        station = Station()
        _fill_station(station, form)
        if _save_photo(station, form):
            db.session.add(station)
            db.session.commit()
            flash(f"«{station.name}» станциясы қосылды.", "success")
            return redirect(url_for("stations.detail", station_id=station.id))
    return render_template("stations/form.html", form=form, station=None)


@bp.route("/<int:station_id>/edit", methods=["GET", "POST"])
@admin_required
def edit(station_id):
    station = db.get_or_404(Station, station_id)
    form = StationForm(obj=station, station=station)
    if request.method == "GET":
        form.parameter_ids.data = [p.id for p in station.parameters]
    if form.validate_on_submit():
        _fill_station(station, form)
        if _save_photo(station, form):
            db.session.commit()
            flash("Станция мәліметтері жаңартылды.", "success")
            return redirect(url_for("stations.detail", station_id=station.id))
        db.session.rollback()
    return render_template("stations/form.html", form=form, station=station)


@bp.route("/<int:station_id>/delete", methods=["POST"])
@admin_required
def delete(station_id):
    station = db.get_or_404(Station, station_id)
    attachments = [a for (a,) in station.observations.with_entities(Observation.attachment) if a]
    name, photo = station.name, station.photo
    db.session.delete(station)
    db.session.commit()
    for path in [photo, *attachments]:
        delete_upload(path)
    flash(f"«{name}» станциясы және оның бақылаулары өшірілді.", "info")
    return redirect(url_for("stations.list_stations"))

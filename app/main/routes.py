from datetime import date, timedelta

from flask import flash, render_template, request

from .. import db
from ..models import Observation, Parameter, Station, User
from ..services import (
    build_line_chart,
    daily_averages,
    latest_conditions,
    parameter_averages,
    parse_date,
    station_averages,
)
from . import bp


@bp.route("/")
def index():
    counts = {
        "stations": Station.query.filter_by(is_active=True).count(),
        "observations": Observation.query.count(),
        "parameters": Parameter.query.count(),
        "users": User.query.count(),
    }
    today = date.today()
    latest = Observation.query.order_by(Observation.observed_at.desc()).limit(8).all()
    week_averages = parameter_averages(date_from=today - timedelta(days=6), date_to=today)
    stations = Station.query.filter_by(is_active=True).order_by(Station.name).all()
    conditions = latest_conditions()
    now_stations = [(s, conditions[s.id]) for s in stations if s.id in conditions][:4]
    return render_template(
        "index.html",
        counts=counts,
        latest=latest,
        week_averages=week_averages,
        stations=stations[:6],
        conditions=conditions,
        now_stations=now_stations,
    )


@bp.route("/stats")
def stats():
    """Орташа мәндер беті: күн аралығы, станция және параметр бойынша сүзгі."""
    today = date.today()
    station_id = request.args.get("station_id", type=int)
    parameter_id = request.args.get("parameter_id", type=int)
    date_from = parse_date(request.args.get("date_from"))
    date_to = parse_date(request.args.get("date_to"))

    if date_from is None and date_to is None:
        date_from, date_to = today - timedelta(days=13), today
    if date_from and date_to and date_from > date_to:
        flash("Басталу күні аяқталу күнінен кейін болмауы керек — күндер ауыстырылды.", "warning")
        date_from, date_to = date_to, date_from

    parameters = Parameter.query.order_by(Parameter.name).all()
    parameter = db.session.get(Parameter, parameter_id) if parameter_id else None
    if parameter is None:
        parameter = Parameter.query.filter_by(code="temperature").first() or (parameters[0] if parameters else None)

    station = db.session.get(Station, station_id) if station_id else None
    summary = parameter_averages(station.id if station else None, date_from, date_to)
    daily, by_station = [], []
    if parameter:
        daily = daily_averages(parameter.id, station.id if station else None, date_from, date_to)
        by_station = station_averages(parameter.id, date_from, date_to)

    return render_template(
        "stats.html",
        stations=Station.query.order_by(Station.name).all(),
        parameters=parameters,
        station=station,
        parameter=parameter,
        date_from=date_from,
        date_to=date_to,
        summary=summary,
        daily=daily,
        chart=build_line_chart(daily),
        by_station=by_station,
    )

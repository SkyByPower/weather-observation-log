"""Бақылау деректерін тексеру, күн бойынша сүзу және орташа мәндерді есептеу."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import func

from . import db
from .models import Observation, Parameter, Station


def parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def apply_date_filter(query, date_from=None, date_to=None):
    if date_from:
        query = query.filter(Observation.observed_at >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.filter(Observation.observed_at < datetime.combine(date_to + timedelta(days=1), time.min))
    return query


def check_observation(station, parameter, value, observed_at):
    """Форма мен API үшін ортақ бизнес-ережелер. {өріс: қате} сөздігін қайтарады."""
    errors = {}
    if station is None:
        errors["station_id"] = "Станция табылмады."
    if parameter is None:
        errors["parameter_id"] = "Параметр табылмады."
    if station and parameter and station.parameters and parameter not in station.parameters:
        errors["parameter_id"] = f"«{station.name}» станциясы бұл параметрді өлшемейді."
    if parameter and value is not None and not parameter.min_value <= value <= parameter.max_value:
        errors["value"] = (
            f"{parameter.name} мәні {parameter.min_value:g}…{parameter.max_value:g} "
            f"{parameter.unit} аралығында болуы керек."
        )
    if observed_at and observed_at > datetime.now() + timedelta(minutes=5):
        errors["observed_at"] = "Болашақ уақытты енгізуге болмайды."
    return errors


def parameter_averages(station_id=None, date_from=None, date_to=None):
    """Әр параметр бойынша орташа / мин / макс мән және бақылау саны."""
    query = db.session.query(
        Parameter.id,
        Parameter.name,
        Parameter.code,
        Parameter.unit,
        func.avg(Observation.value).label("avg"),
        func.min(Observation.value).label("min"),
        func.max(Observation.value).label("max"),
        func.count(Observation.id).label("count"),
    ).join(Observation, Observation.parameter_id == Parameter.id)
    if station_id:
        query = query.filter(Observation.station_id == station_id)
    query = apply_date_filter(query, date_from, date_to)
    return query.group_by(Parameter.id).order_by(Parameter.name).all()


def daily_averages(parameter_id, station_id=None, date_from=None, date_to=None):
    """Таңдалған параметрдің күндік орташа мәндері (график үшін)."""
    day = func.date(Observation.observed_at)
    query = db.session.query(
        day.label("day"),
        func.avg(Observation.value).label("avg"),
        func.min(Observation.value).label("min"),
        func.max(Observation.value).label("max"),
        func.count(Observation.id).label("count"),
    ).filter(Observation.parameter_id == parameter_id)
    if station_id:
        query = query.filter(Observation.station_id == station_id)
    query = apply_date_filter(query, date_from, date_to)
    rows = query.group_by(day).order_by(day).all()
    return [
        {
            "date": row.day if isinstance(row.day, date) else date.fromisoformat(str(row.day)),
            "avg": row.avg,
            "min": row.min,
            "max": row.max,
            "count": row.count,
        }
        for row in rows
    ]


def station_averages(parameter_id, date_from=None, date_to=None):
    """Бір параметр бойынша станцияларды салыстыру."""
    query = db.session.query(
        Station.id,
        Station.name,
        func.avg(Observation.value).label("avg"),
        func.count(Observation.id).label("count"),
    ).join(Observation, Observation.station_id == Station.id).filter(Observation.parameter_id == parameter_id)
    query = apply_date_filter(query, date_from, date_to)
    return query.group_by(Station.id).order_by(func.avg(Observation.value).desc()).all()


def build_line_chart(daily, width=760, height=260, pad_x=48, pad_y=28):
    """Күндік орташа мәндерден SVG сызықтық графигінің координаталарын есептейді."""
    if not daily:
        return None
    values = [d["avg"] for d in daily]
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        lo, hi = lo - 1, hi + 1
    margin = (hi - lo) * 0.1
    lo, hi = lo - margin, hi + margin

    inner_w, inner_h = width - 2 * pad_x, height - 2 * pad_y
    step = inner_w / (len(daily) - 1) if len(daily) > 1 else 0

    def y_of(v):
        return round(pad_y + (hi - v) / (hi - lo) * inner_h, 1)

    points = []
    for i, d in enumerate(daily):
        x = round(pad_x + i * step, 1) if len(daily) > 1 else width / 2
        points.append({"x": x, "y": y_of(d["avg"]), **d})

    label_every = max(1, len(daily) // 10)
    ticks = [{"y": y_of(lo + (hi - lo) * k / 4), "value": lo + (hi - lo) * k / 4} for k in range(5)]
    return {
        "width": width,
        "height": height,
        "pad_x": pad_x,
        "pad_y": pad_y,
        "points": points,
        "polyline": " ".join(f"{p['x']},{p['y']}" for p in points),
        "area": f"{points[0]['x']},{height - pad_y} "
        + " ".join(f"{p['x']},{p['y']}" for p in points)
        + f" {points[-1]['x']},{height - pad_y}",
        "ticks": ticks,
        "label_every": label_every,
    }

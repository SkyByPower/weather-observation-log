"""JSON API. Оқу (GET) — ашық, жазу (POST/PUT/DELETE) — X-API-Key тақырыбы арқылы."""
from datetime import datetime
from functools import wraps

from flask import current_app, g, jsonify, request, url_for
from sqlalchemy import or_

from .. import db
from ..i18n import gettext as _
from ..models import Observation, Parameter, Station, User
from ..services import apply_date_filter, check_observation, daily_averages, parameter_averages, parse_date
from ..utils import delete_upload
from . import bp


def error(status, message, details=None):
    payload = {"error": message, "status": status}
    if details:
        payload["details"] = details
    return jsonify(payload), status


def token_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        token = request.headers.get("X-API-Key", "")
        auth = request.headers.get("Authorization", "")
        if not token and auth.startswith("Bearer "):
            token = auth[len("Bearer "):]
        user = User.query.filter_by(api_token=token).first() if token else None
        if user is None:
            return error(401, _("API кілті жоқ немесе жарамсыз. «X-API-Key» тақырыбын жіберіңіз."))
        g.api_user = user
        return view(*args, **kwargs)

    return wrapper


def _find_parameter(value):
    """Параметрді id (сан) немесе code (мәтін) бойынша табады."""
    if value is None or value == "":
        return None
    if isinstance(value, int) or str(value).isdigit():
        return db.session.get(Parameter, int(value))
    return Parameter.query.filter_by(code=str(value)).first()


def _parse_datetime(value):
    dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def _validate_payload(data, observation=None):
    """POST үшін барлық өріс керек, PUT үшін тек жіберілгендері өзгереді."""
    errors = {}
    partial = observation is not None
    station = observation.station if partial else None
    parameter = observation.parameter if partial else None
    value = observation.value if partial else None
    observed_at = observation.observed_at if partial else datetime.now().replace(second=0, microsecond=0)
    note = observation.note if partial else None

    if "station_id" in data or not partial:
        try:
            station = db.session.get(Station, int(data.get("station_id")))
        except (TypeError, ValueError):
            errors["station_id"] = _("station_id бүтін сан болуы керек.")
    if "parameter_id" in data or "parameter" in data or not partial:
        parameter = _find_parameter(data.get("parameter_id", data.get("parameter")))
    if "value" in data or not partial:
        raw = data.get("value")
        if isinstance(raw, bool) or raw is None:
            errors["value"] = _("value — міндетті сандық өріс.")
        else:
            try:
                value = float(raw)
            except (TypeError, ValueError):
                errors["value"] = _("value сан болуы керек.")
    if data.get("observed_at"):
        try:
            observed_at = _parse_datetime(data["observed_at"])
        except ValueError:
            errors["observed_at"] = _("observed_at ISO 8601 форматында болуы керек (мыс. 2026-10-30T14:00).")
    if "note" in data:
        note = (str(data["note"]).strip() if data["note"] is not None else "") or None
        if note and len(note) > 500:
            errors["note"] = _("note ең көбі 500 таңба.")

    for field, message in check_observation(station, parameter, value, observed_at).items():
        errors.setdefault(field, message)
    if errors:
        return None, errors
    return {"station": station, "parameter": parameter, "value": value, "observed_at": observed_at, "note": note}, None


def _json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


@bp.get("/")
def index():
    return jsonify(
        {
            "name": "Weather Observation Log API",
            "endpoints": {
                "GET /api/stations": _("Станциялар тізімі (?q=, ?city=)"),
                "GET /api/stations/<id>": _("Бір станция + параметрлері"),
                "GET /api/parameters": _("Параметрлер тізімі"),
                "GET /api/observations": _("Бақылаулар (?station_id, ?parameter, ?date_from, ?date_to, ?page, ?per_page)"),
                "GET /api/observations/<id>": _("Бір бақылау"),
                "POST /api/observations": _("Жаңа бақылау (X-API-Key керек)"),
                "PUT /api/observations/<id>": _("Бақылауды өзгерту (X-API-Key, автор немесе admin)"),
                "DELETE /api/observations/<id>": _("Бақылауды өшіру (X-API-Key, автор немесе admin)"),
                "GET /api/stats/averages": _("Орташа мәндер (?station_id, ?parameter, ?date_from, ?date_to)"),
            },
        }
    )


@bp.get("/stations")
def list_stations():
    query = Station.query
    if q := request.args.get("q", "").strip():
        like = f"%{q}%"
        query = query.filter(or_(Station.name.ilike(like), Station.code.ilike(like), Station.city.ilike(like)))
    if city := request.args.get("city", "").strip():
        query = query.filter(Station.city == city)
    stations = query.order_by(Station.name).all()
    return jsonify({"count": len(stations), "items": [s.to_dict() for s in stations]})


@bp.get("/stations/<int:station_id>")
def get_station(station_id):
    return jsonify(db.get_or_404(Station, station_id).to_dict(with_parameters=True))


@bp.get("/parameters")
def list_parameters():
    parameters = Parameter.query.order_by(Parameter.name).all()
    return jsonify({"count": len(parameters), "items": [p.to_dict() for p in parameters]})


@bp.get("/observations")
def list_observations():
    query = Observation.query
    if station_id := request.args.get("station_id", type=int):
        query = query.filter(Observation.station_id == station_id)
    if "parameter" in request.args or "parameter_id" in request.args:
        parameter = _find_parameter(request.args.get("parameter_id") or request.args.get("parameter"))
        if parameter is None:
            return error(404, _("Параметр табылмады."))
        query = query.filter(Observation.parameter_id == parameter.id)
    for name in ("date_from", "date_to"):
        if request.args.get(name) and parse_date(request.args.get(name)) is None:
            return error(400, _("{name} форматы YYYY-MM-DD болуы керек.", name=name))
    query = apply_date_filter(query, parse_date(request.args.get("date_from")), parse_date(request.args.get("date_to")))

    per_page = min(max(request.args.get("per_page", 20, type=int), 1), current_app.config["API_MAX_PER_PAGE"])
    page = max(request.args.get("page", 1, type=int), 1)
    pagination = query.order_by(Observation.observed_at.desc(), Observation.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify(
        {
            "items": [o.to_dict() for o in pagination.items],
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
        }
    )


@bp.get("/observations/<int:observation_id>")
def get_observation(observation_id):
    return jsonify(db.get_or_404(Observation, observation_id).to_dict())


@bp.post("/observations")
@token_required
def create_observation():
    data = _json_body()
    if data is None:
        return error(400, _("Сұраныс денесі JSON объект болуы керек."))
    cleaned, errors = _validate_payload(data)
    if errors:
        return error(422, _("Деректер қате."), errors)
    observation = Observation(
        station=cleaned["station"],
        parameter=cleaned["parameter"],
        value=cleaned["value"],
        observed_at=cleaned["observed_at"],
        note=cleaned["note"],
        author=g.api_user,
    )
    db.session.add(observation)
    db.session.commit()
    response = jsonify(observation.to_dict())
    response.status_code = 201
    response.headers["Location"] = url_for("api.get_observation", observation_id=observation.id)
    return response


@bp.put("/observations/<int:observation_id>")
@token_required
def update_observation(observation_id):
    observation = db.get_or_404(Observation, observation_id)
    if not observation.can_edit(g.api_user):
        return error(403, _("Бұл жазбаны тек авторы немесе admin өзгерте алады."))
    data = _json_body()
    if data is None:
        return error(400, _("Сұраныс денесі JSON объект болуы керек."))
    cleaned, errors = _validate_payload(data, observation)
    if errors:
        return error(422, _("Деректер қате."), errors)
    observation.station = cleaned["station"]
    observation.parameter = cleaned["parameter"]
    observation.value = cleaned["value"]
    observation.observed_at = cleaned["observed_at"]
    observation.note = cleaned["note"]
    db.session.commit()
    return jsonify(observation.to_dict())


@bp.delete("/observations/<int:observation_id>")
@token_required
def delete_observation(observation_id):
    observation = db.get_or_404(Observation, observation_id)
    if not observation.can_edit(g.api_user):
        return error(403, _("Бұл жазбаны тек авторы немесе admin өшіре алады."))
    attachment = observation.attachment
    db.session.delete(observation)
    db.session.commit()
    delete_upload(attachment)
    return jsonify({"message": _("Бақылау өшірілді."), "id": observation_id})


@bp.get("/stats/averages")
def averages():
    station_id = request.args.get("station_id", type=int)
    date_from = parse_date(request.args.get("date_from"))
    date_to = parse_date(request.args.get("date_to"))
    result = {
        "station_id": station_id,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "by_parameter": [
            {
                "parameter": row.code,
                "name": row.name,
                "unit": row.unit,
                "avg": round(row.avg, 2),
                "min": row.min,
                "max": row.max,
                "count": row.count,
            }
            for row in parameter_averages(station_id, date_from, date_to)
        ],
    }
    if "parameter" in request.args:
        parameter = _find_parameter(request.args["parameter"])
        if parameter is None:
            return error(404, _("Параметр табылмады."))
        result["daily"] = [
            {"date": d["date"].isoformat(), "avg": round(d["avg"], 2), "min": d["min"], "max": d["max"], "count": d["count"]}
            for d in daily_averages(parameter.id, station_id, date_from, date_to)
        ]
    return jsonify(result)

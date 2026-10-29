import io
from datetime import date, datetime, timedelta

from app import db
from app.models import Observation, Parameter, Station, User

from .conftest import login

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _param(code):
    return Parameter.query.filter_by(code=code).one()


def _station(code="ALA-01"):
    return Station.query.filter_by(code=code).one()


def _obs_form(**overrides):
    data = {
        "station_id": _station().id,
        "parameter_id": _param("temperature").id,
        "value": "7,5",
        "observed_at": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "note": "Тест бақылауы",
    }
    data.update(overrides)
    return data


# ---------- Аутентификация ----------

def test_register_login_logout(client):
    resp = client.post(
        "/auth/register",
        data={"username": "newbie", "email": "newbie@test.kz", "password": "secret1", "confirm": "secret1"},
        follow_redirects=True,
    )
    assert "Тіркелу сәтті өтті" in resp.get_data(as_text=True)
    assert User.query.filter_by(username="newbie").one().role == "user"

    resp = login(client, "newbie", "secret1")
    assert "Қош келдіңіз, newbie" in resp.get_data(as_text=True)

    resp = client.post("/auth/logout", follow_redirects=True)
    assert "Сіз жүйеден шықтыңыз" in resp.get_data(as_text=True)


def test_register_validation(client):
    resp = client.post(
        "/auth/register",
        data={"username": "ab", "email": "not-an-email", "password": "123", "confirm": "456"},
    )
    text = resp.get_data(as_text=True)
    assert "3–30 таңба" in text
    assert "Email адресі дұрыс емес" in text
    assert "кемінде 6 таңба" in text
    assert "Құпиясөздер сәйкес емес" in text


def test_wrong_password(client):
    assert "қате" in login(client, "admin", "wrong").get_data(as_text=True)


def test_login_redirect_rejects_external_next(client):
    resp = client.post(
        "/auth/login?next=https://evil.example", data={"username": "user", "password": "user123"}
    )
    assert resp.headers["Location"] == "/"


# ---------- Рөлдер ----------

def test_anonymous_is_redirected_to_login(client):
    resp = client.get("/observations/new")
    assert resp.status_code == 302 and "/auth/login" in resp.headers["Location"]


def test_user_cannot_access_admin_pages(user_client):
    assert user_client.get("/stations/new").status_code == 403
    assert user_client.get("/admin/users").status_code == 403
    assert user_client.get("/admin/parameters").status_code == 403


def test_admin_can_change_role(admin_client):
    target = User.query.filter_by(username="user").one()
    admin_client.post(f"/admin/users/{target.id}/role", data={"role": "admin"})
    assert db.session.get(User, target.id).role == "admin"


# ---------- Станция CRUD + файл жүктеу ----------

def test_station_crud_with_photo(admin_client, app):
    data = {
        "name": "Тест станциясы", "code": "TST-01", "city": "Тараз", "latitude": "42.9", "longitude": "71.37",
        "elevation": "650", "phone": "+7 7262 43 00 00", "email": "tst@test.kz",
        "parameter_ids": [_param("temperature").id], "is_active": "y",
        "photo_file": (io.BytesIO(PNG_BYTES), "my photo.png"),
    }
    resp = admin_client.post("/stations/new", data=data, content_type="multipart/form-data", follow_redirects=True)
    assert "станциясы қосылды" in resp.get_data(as_text=True)
    station = Station.query.filter_by(code="TST-01").one()
    assert station.photo.startswith("stations/") and station.photo.endswith(".png")
    assert " " not in station.photo

    resp = admin_client.post(
        f"/stations/{station.id}/edit",
        data={**data, "photo_file": (io.BytesIO(b""), ""), "city": "Жамбыл облысы"},
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert db.session.get(Station, station.id).city == "Жамбыл облысы"

    admin_client.post(f"/stations/{station.id}/delete")
    assert db.session.get(Station, station.id) is None


def test_station_validation_and_bad_upload(admin_client):
    data = {
        "name": "X", "code": "bad code", "city": "Тараз", "latitude": "123", "longitude": "abc",
        "phone": "телефон", "photo_file": (io.BytesIO(b"MZ..."), "virus.exe"),
    }
    text = admin_client.post("/stations/new", data=data, content_type="multipart/form-data").get_data(as_text=True)
    assert "−90…90" in text
    assert "Сан енгізіңіз" in text
    assert "Телефон форматы дұрыс емес" in text
    assert "Тек сурет файлдары" in text


def test_fake_image_rejected(admin_client):
    data = {
        "name": "Жалған сурет", "code": "FAKE-1", "city": "Тараз", "latitude": "42", "longitude": "71",
        "photo_file": (io.BytesIO(b"<script>alert(1)</script>"), "photo.png"),
    }
    text = admin_client.post("/stations/new", data=data, content_type="multipart/form-data").get_data(as_text=True)
    assert "мазмұны кеңейтіміне сәйкес келмейді" in text
    assert Station.query.filter_by(code="FAKE-1").first() is None


# ---------- Бақылау CRUD + валидация ----------

def test_observation_crud(user_client):
    resp = user_client.post(
        "/observations/new",
        data={**_obs_form(), "attachment_file": (io.BytesIO(b"%PDF-1.4 test"), "report.pdf")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert "Бақылау жазбасы қосылды" in resp.get_data(as_text=True)
    obs = Observation.query.filter_by(note="Тест бақылауы").one()
    assert obs.value == 7.5 and obs.attachment.endswith(".pdf")

    assert user_client.get(f"/observations/{obs.id}").status_code == 200

    user_client.post(f"/observations/{obs.id}/edit", data=_obs_form(value="9.1"), follow_redirects=True)
    assert db.session.get(Observation, obs.id).value == 9.1

    user_client.post(f"/observations/{obs.id}/delete")
    assert db.session.get(Observation, obs.id) is None


def test_observation_value_range_and_future_date(user_client):
    future = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
    text = user_client.post("/observations/new", data=_obs_form(value="99", observed_at=future)).get_data(as_text=True)
    assert "-60…60" in text
    assert "Болашақ уақытты" in text


def test_station_must_measure_parameter(user_client):
    burabay = _station("BUR-01")  # қысымды өлшемейді
    text = user_client.post(
        "/observations/new",
        data=_obs_form(station_id=burabay.id, parameter_id=_param("pressure").id, value="1010"),
    ).get_data(as_text=True)
    assert "бұл параметрді өлшемейді" in text


def test_user_cannot_edit_others_observation(user_client):
    admin = User.query.filter_by(username="admin").one()
    obs = Observation.query.filter_by(user_id=admin.id).first()
    assert user_client.get(f"/observations/{obs.id}/edit").status_code == 403
    assert user_client.post(f"/observations/{obs.id}/delete").status_code == 403


# ---------- Іздеу, сүзгі, сорттау, пагинация ----------

def test_search_filter_sort_and_pagination(client):
    station = _station("AST-01")
    temp = _param("temperature")
    day = (date.today() - timedelta(days=1)).isoformat()  # кешегі күн толық болады
    resp = client.get(
        f"/observations/?station_id={station.id}&parameter_id={temp.id}&date_from={day}&date_to={day}&sort=value_desc"
    )
    text = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "орташа" in text  # сүзілген деректердің орташа мәні

    resp = client.get("/observations/?q=Медеу&page=2")
    assert resp.status_code == 200 and "Медеу" in resp.get_data(as_text=True)
    assert "2/" in client.get("/observations/?page=2").get_data(as_text=True)

    assert "Медеу тау станциясы" in client.get("/stations/?q=медеу").get_data(as_text=True)


def test_stats_page_and_averages(client):
    resp = client.get(f"/stats?station_id={_station().id}")
    text = resp.get_data(as_text=True)
    assert resp.status_code == 200 and "<svg" in text and "Станциялар салыстыруы" in text


# ---------- Қате беттері ----------

def test_custom_404(client):
    resp = client.get("/no-such-page")
    assert resp.status_code == 404 and "Бет табылмады" in resp.get_data(as_text=True)
    assert client.get("/stations/99999").status_code == 404


def test_custom_500(app, client):
    @app.route("/boom")
    def boom():
        raise RuntimeError("test")

    app.config["PROPAGATE_EXCEPTIONS"] = False
    resp = client.get("/boom")
    assert resp.status_code == 500 and "Сервердің ішкі қатесі" in resp.get_data(as_text=True)


# ---------- API ----------

def test_api_read_endpoints(client):
    assert client.get("/api/stations").get_json()["count"] == 7
    assert len(client.get("/api/parameters").get_json()["items"]) == 5
    data = client.get("/api/observations?parameter=temperature&per_page=5").get_json()
    assert len(data["items"]) == 5 and data["items"][0]["parameter"]["code"] == "temperature"
    stats = client.get("/api/stats/averages?parameter=temperature").get_json()
    assert stats["by_parameter"] and stats["daily"]
    assert client.get("/api/observations/999999").status_code == 404
    assert client.get("/api/observations/999999").get_json()["status"] == 404


def test_api_write_requires_token(client):
    resp = client.post("/api/observations", json={"station_id": 1, "parameter": "temperature", "value": 1})
    assert resp.status_code == 401


def test_api_create_update_delete(client, user_token, admin_token):
    headers = {"X-API-Key": user_token}
    resp = client.post(
        "/api/observations",
        json={"station_id": _station().id, "parameter": "humidity", "value": 64, "note": "API арқылы"},
        headers=headers,
    )
    assert resp.status_code == 201
    obs_id = resp.get_json()["id"]

    resp = client.put(f"/api/observations/{obs_id}", json={"value": 70}, headers=headers)
    assert resp.status_code == 200 and resp.get_json()["value"] == 70

    resp = client.put(f"/api/observations/{obs_id}", json={"value": 170}, headers=headers)
    assert resp.status_code == 422 and "value" in resp.get_json()["details"]

    assert client.delete(f"/api/observations/{obs_id}", headers={"X-API-Key": admin_token}).status_code == 200
    assert client.get(f"/api/observations/{obs_id}").status_code == 404


def test_api_forbids_editing_others(client, user_token):
    admin = User.query.filter_by(username="admin").one()
    obs = Observation.query.filter_by(user_id=admin.id).first()
    resp = client.delete(f"/api/observations/{obs.id}", headers={"X-API-Key": user_token})
    assert resp.status_code == 403

import re
from pathlib import Path

from app.translations_ru import RU

from .conftest import login

APP = Path(__file__).resolve().parent.parent / "app"
PY_CALL = re.compile(r'\b_l?\(\s*"((?:[^"\\]|\\.)*)"')
TPL_CALL = re.compile(r"\b_\(\s*(['\"])(.*?)\1")


def collect_keys():
    """Кодта және шаблондарда _() / _l() арқылы аударылатын барлық мәтін."""
    keys = set()
    for path in APP.rglob("*.py"):
        keys.update(PY_CALL.findall(path.read_text(encoding="utf-8")))
    for path in (APP / "templates").rglob("*.html"):
        keys.update(text for _quote, text in TPL_CALL.findall(path.read_text(encoding="utf-8")))
    return keys


def test_every_string_has_russian_translation():
    missing = sorted(collect_keys() - RU.keys())
    assert not missing, "Аудармасы жоқ мәтіндер:\n" + "\n".join(missing)


def test_placeholders_match():
    for kk, ru in RU.items():
        assert set(re.findall(r"\{\w+\}", kk)) == set(re.findall(r"\{\w+\}", ru)), kk
        assert set(re.findall(r"%\(\w+\)d", kk)) == set(re.findall(r"%\(\w+\)d", ru)), kk


def test_switch_to_russian_and_back(client):
    assert "Станциялар" in client.get("/").get_data(as_text=True)

    resp = client.get("/lang/ru", headers={"Referer": "http://localhost/stations/"})
    assert resp.status_code == 302 and resp.headers["Location"] == "/stations/"
    text = client.get("/stations/").get_data(as_text=True)
    assert 'lang="ru"' in text and "Метеостанции" in text and "Алматинская метеостанция" in text

    client.get("/lang/kk")
    assert "Метеостанциялар" in client.get("/stations/").get_data(as_text=True)


def test_russian_validation_and_flash_messages(client):
    client.get("/lang/ru")
    text = client.post(
        "/auth/register", data={"username": "ab", "email": "x", "password": "1", "confirm": "2"}
    ).get_data(as_text=True)
    assert "Длина должна быть от 3 до 30 символов." in text
    assert "Некорректный адрес email." in text
    assert "Пароли не совпадают." in text

    assert "Добро пожаловать, admin!" in login(client, "admin", "admin123").get_data(as_text=True)


def test_unknown_language_is_ignored(client):
    client.get("/lang/xx")
    assert 'lang="kk"' in client.get("/").get_data(as_text=True)


def test_language_switch_does_not_redirect_to_other_sites(client):
    resp = client.get("/lang/ru", headers={"Referer": "https://evil.example/phish"})
    assert resp.headers["Location"] == "/"

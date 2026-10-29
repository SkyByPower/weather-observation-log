import pytest

from app import create_app, db
from app.models import User
from app.seed import seed_demo_data


@pytest.fixture()
def app():
    app = create_app("config.TestingConfig")
    with app.app_context():
        db.create_all()
        seed_demo_data(days=5)
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, username, password):
    return client.post("/auth/login", data={"username": username, "password": password}, follow_redirects=True)


@pytest.fixture()
def admin_client(client):
    login(client, "admin", "admin123")
    return client


@pytest.fixture()
def user_client(client):
    login(client, "user", "user123")
    return client


@pytest.fixture()
def user_token(app):
    return User.query.filter_by(username="user").one().api_token


@pytest.fixture()
def admin_token(app):
    return User.query.filter_by(username="admin").one().api_token

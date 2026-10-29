import click

from . import db
from .models import ROLE_ADMIN, User


def register_commands(app):
    @app.cli.command("init-db")
    @click.option("--drop", is_flag=True, help="Алдымен барлық кестелерді өшіру.")
    def init_db(drop):
        """Дерекқор кестелерін жасау."""
        if drop:
            db.drop_all()
            click.echo("Кестелер өшірілді.")
        db.create_all()
        click.echo("Дерекқор дайын.")

    @app.cli.command("seed")
    @click.option("--days", default=30, show_default=True, help="Неше күндік демо-бақылау жасау.")
    def seed(days):
        """Дерекқорды қайта жасап, демо деректермен толтыру."""
        from .seed import seed_demo_data

        db.drop_all()
        db.create_all()
        stats = seed_demo_data(days)
        click.echo(
            f"Дайын: {stats['users']} пайдаланушы, {stats['stations']} станция, "
            f"{stats['parameters']} параметр, {stats['observations']} бақылау."
        )
        click.echo("Тест аккаунттар: admin / admin123 (admin), user / user123 (user)")

    @app.cli.command("create-admin")
    @click.option("--username", prompt="Пайдаланушы аты")
    @click.option("--email", prompt="Email")
    @click.option("--password", prompt="Құпиясөз", hide_input=True, confirmation_prompt=True)
    def create_admin(username, email, password):
        """Жаңа admin аккаунтын жасау."""
        if User.query.filter((User.username == username) | (User.email == email)).first():
            raise click.ClickException("Мұндай пайдаланушы аты немесе email бар.")
        if len(password) < 6:
            raise click.ClickException("Құпиясөз кемінде 6 таңба болуы керек.")
        user = User(username=username, email=email.lower(), role=ROLE_ADMIN)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Admin «{username}» жасалды.")

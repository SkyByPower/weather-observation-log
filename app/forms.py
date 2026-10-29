from datetime import datetime

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from sqlalchemy import func
from wtforms import (
    BooleanField,
    DateTimeLocalField,
    FloatField,
    PasswordField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)
from wtforms.widgets import CheckboxInput, ListWidget, TextInput

from . import db
from .models import Parameter, Station, User
from .services import check_observation
from .utils import DOCUMENT_EXTENSIONS, IMAGE_EXTENSIONS

REQUIRED = "Бұл өріс міндетті."
PHONE_RE = r"^\+?[0-9][0-9\s\-()]{6,19}$"


class DecimalCommaFloatField(FloatField):
    """Үтірмен жазылған санды да қабылдайды (мыс. 12,5)."""

    widget = TextInput()

    def process_formdata(self, valuelist):
        if not valuelist or not valuelist[0].strip():
            self.data = None
            return
        try:
            self.data = float(valuelist[0].strip().replace(",", "."))
        except ValueError:
            self.data = None
            raise ValueError("Сан енгізіңіз.")


class MultiCheckboxField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


class LoginForm(FlaskForm):
    username = StringField("Пайдаланушы аты", validators=[DataRequired(REQUIRED), Length(max=30)])
    password = PasswordField("Құпиясөз", validators=[DataRequired(REQUIRED)])
    remember = BooleanField("Мені есте сақта")
    submit = SubmitField("Кіру")


class RegisterForm(FlaskForm):
    username = StringField(
        "Пайдаланушы аты",
        validators=[
            DataRequired(REQUIRED),
            Length(3, 30, message="Ұзындығы 3–30 таңба болуы керек."),
            Regexp(r"^[A-Za-z0-9_.]+$", message="Тек латын әріптері, сандар, «_» және «.» рұқсат."),
        ],
    )
    email = StringField(
        "Email",
        validators=[DataRequired(REQUIRED), Email(message="Email адресі дұрыс емес."), Length(max=120)],
    )
    password = PasswordField(
        "Құпиясөз",
        validators=[DataRequired(REQUIRED), Length(6, 128, message="Құпиясөз кемінде 6 таңба болуы керек.")],
    )
    confirm = PasswordField(
        "Құпиясөзді қайталаңыз",
        validators=[DataRequired(REQUIRED), EqualTo("password", message="Құпиясөздер сәйкес емес.")],
    )
    submit = SubmitField("Тіркелу")

    def validate_username(self, field):
        if User.query.filter(func.lower(User.username) == field.data.strip().lower()).first():
            raise ValidationError("Бұл атпен пайдаланушы бұрыннан бар.")

    def validate_email(self, field):
        if User.query.filter(func.lower(User.email) == field.data.strip().lower()).first():
            raise ValidationError("Бұл email бұрыннан тіркелген.")


class StationForm(FlaskForm):
    name = StringField("Атауы", validators=[DataRequired(REQUIRED), Length(2, 100)])
    code = StringField(
        "Коды",
        validators=[
            DataRequired(REQUIRED),
            Length(2, 20),
            Regexp(r"^[A-Z0-9-]+$", message="Тек бас латын әріптері, сандар және «-» (мыс. ALA-01)."),
        ],
    )
    city = StringField("Қала / өңір", validators=[DataRequired(REQUIRED), Length(2, 100)])
    latitude = DecimalCommaFloatField(
        "Ендік", validators=[InputRequired(REQUIRED), NumberRange(-90, 90, "Ендік −90…90 аралығында болуы керек.")]
    )
    longitude = DecimalCommaFloatField(
        "Бойлық",
        validators=[InputRequired(REQUIRED), NumberRange(-180, 180, "Бойлық −180…180 аралығында болуы керек.")],
    )
    elevation = DecimalCommaFloatField(
        "Биіктік (м)", validators=[Optional(), NumberRange(-500, 9000, "Биіктік −500…9000 м аралығында болуы керек.")]
    )
    phone = StringField(
        "Телефон",
        validators=[Optional(), Regexp(PHONE_RE, message="Телефон форматы дұрыс емес (мыс. +7 727 123 45 67).")],
    )
    email = StringField("Email", validators=[Optional(), Email(message="Email адресі дұрыс емес."), Length(max=120)])
    description = TextAreaField("Сипаттама", validators=[Optional(), Length(max=1000)])
    parameter_ids = MultiCheckboxField("Өлшенетін параметрлер", coerce=int)
    is_active = BooleanField("Белсенді станция", default=True)
    photo_file = FileField(
        "Фото (PNG, JPG, GIF, WEBP — 5 МБ дейін)",
        validators=[FileAllowed(sorted(IMAGE_EXTENSIONS), "Тек сурет файлдары рұқсат етіледі.")],
    )
    submit = SubmitField("Сақтау")

    def __init__(self, *args, station=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._station = station
        self.parameter_ids.choices = [
            (p.id, f"{p.name} ({p.unit})") for p in Parameter.query.order_by(Parameter.name)
        ]

    def _ensure_unique(self, column, value, message):
        query = Station.query.filter(func.lower(column) == value.strip().lower())
        if self._station is not None:
            query = query.filter(Station.id != self._station.id)
        if query.first():
            raise ValidationError(message)

    def validate_name(self, field):
        self._ensure_unique(Station.name, field.data, "Бұл атаумен станция бұрыннан бар.")

    def validate_code(self, field):
        self._ensure_unique(Station.code, field.data, "Бұл кодпен станция бұрыннан бар.")


class ParameterForm(FlaskForm):
    name = StringField("Атауы", validators=[DataRequired(REQUIRED), Length(2, 60)])
    code = StringField(
        "Коды (латынша)",
        validators=[
            DataRequired(REQUIRED),
            Length(2, 30),
            Regexp(r"^[a-z][a-z0-9_]*$", message="Кіші латын әріптері, сандар және «_» (мыс. wind_speed)."),
        ],
    )
    unit = StringField("Өлшем бірлігі", validators=[DataRequired(REQUIRED), Length(1, 20)])
    min_value = DecimalCommaFloatField("Ең кіші рұқсат мән", validators=[InputRequired(REQUIRED)])
    max_value = DecimalCommaFloatField("Ең үлкен рұқсат мән", validators=[InputRequired(REQUIRED)])
    description = TextAreaField("Сипаттама", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Сақтау")

    def __init__(self, *args, parameter=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._parameter = parameter

    def _ensure_unique(self, column, value, message):
        query = Parameter.query.filter(func.lower(column) == value.strip().lower())
        if self._parameter is not None:
            query = query.filter(Parameter.id != self._parameter.id)
        if query.first():
            raise ValidationError(message)

    def validate_name(self, field):
        self._ensure_unique(Parameter.name, field.data, "Бұл атаумен параметр бар.")

    def validate_code(self, field):
        self._ensure_unique(Parameter.code, field.data, "Бұл кодпен параметр бар.")

    def validate_max_value(self, field):
        if self.min_value.data is not None and field.data is not None and field.data <= self.min_value.data:
            raise ValidationError("Ең үлкен мән ең кіші мәннен үлкен болуы керек.")


class ObservationForm(FlaskForm):
    station_id = SelectField("Станция", coerce=int, validators=[InputRequired(REQUIRED)])
    parameter_id = SelectField("Параметр", coerce=int, validators=[InputRequired(REQUIRED)])
    value = DecimalCommaFloatField("Мәні", validators=[InputRequired(REQUIRED)])
    observed_at = DateTimeLocalField(
        "Бақылау уақыты", format="%Y-%m-%dT%H:%M", validators=[InputRequired(REQUIRED)]
    )
    note = TextAreaField("Ескертпе", validators=[Optional(), Length(max=500, message="Ең көбі 500 таңба.")])
    attachment_file = FileField(
        "Тіркеме (PDF, PNG, JPG, CSV, TXT — 5 МБ дейін)",
        validators=[FileAllowed(sorted(DOCUMENT_EXTENSIONS), "Бұл файл түріне рұқсат жоқ.")],
    )
    submit = SubmitField("Сақтау")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.station_id.choices = [
            (s.id, s.name if s.is_active else f"{s.name} (белсенді емес)")
            for s in Station.query.order_by(Station.name)
        ]
        self.parameter_id.choices = [
            (p.id, f"{p.name}, {p.unit}") for p in Parameter.query.order_by(Parameter.name)
        ]

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        errors = check_observation(
            db.session.get(Station, self.station_id.data),
            db.session.get(Parameter, self.parameter_id.data),
            self.value.data,
            self.observed_at.data,
        )
        for field_name, message in errors.items():
            getattr(self, field_name).errors.append(message)
        return not errors

    @property
    def observed_at_max(self):
        return datetime.now().strftime("%Y-%m-%dT%H:%M")

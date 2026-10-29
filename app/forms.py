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
from .i18n import gettext as _
from .i18n import lazy_gettext as _l
from .i18n import translate_data
from .models import Parameter, Station, User
from .services import check_observation
from .utils import DOCUMENT_EXTENSIONS, IMAGE_EXTENSIONS

REQUIRED = _l("Бұл өріс міндетті.")
LENGTH_MSG = _l("Ұзындығы %(min)d–%(max)d таңба болуы керек.")
MAX_LENGTH_MSG = _l("Ең көбі %(max)d таңба.")
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
            raise ValueError(_l("Сан енгізіңіз."))


class MultiCheckboxField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


class LoginForm(FlaskForm):
    username = StringField(_l("Пайдаланушы аты"), validators=[DataRequired(REQUIRED), Length(max=30, message=MAX_LENGTH_MSG)])
    password = PasswordField(_l("Құпиясөз"), validators=[DataRequired(REQUIRED)])
    remember = BooleanField(_l("Мені есте сақта"))
    submit = SubmitField(_l("Кіру"))


class RegisterForm(FlaskForm):
    username = StringField(
        _l("Пайдаланушы аты"),
        validators=[
            DataRequired(REQUIRED),
            Length(3, 30, message=_l("Ұзындығы 3–30 таңба болуы керек.")),
            Regexp(r"^[A-Za-z0-9_.]+$", message=_l("Тек латын әріптері, сандар, «_» және «.» рұқсат.")),
        ],
    )
    email = StringField(
        "Email",
        validators=[DataRequired(REQUIRED), Email(message=_l("Email адресі дұрыс емес.")), Length(max=120, message=MAX_LENGTH_MSG)],
    )
    password = PasswordField(
        _l("Құпиясөз"),
        validators=[DataRequired(REQUIRED), Length(6, 128, message=_l("Құпиясөз кемінде 6 таңба болуы керек."))],
    )
    confirm = PasswordField(
        _l("Құпиясөзді қайталаңыз"),
        validators=[DataRequired(REQUIRED), EqualTo("password", message=_l("Құпиясөздер сәйкес емес."))],
    )
    submit = SubmitField(_l("Тіркелу"))

    def validate_username(self, field):
        if User.query.filter(func.lower(User.username) == field.data.strip().lower()).first():
            raise ValidationError(_l("Бұл атпен пайдаланушы бұрыннан бар."))

    def validate_email(self, field):
        if User.query.filter(func.lower(User.email) == field.data.strip().lower()).first():
            raise ValidationError(_l("Бұл email бұрыннан тіркелген."))


class StationForm(FlaskForm):
    name = StringField(_l("Атауы"), validators=[DataRequired(REQUIRED), Length(2, 100, message=LENGTH_MSG)])
    code = StringField(
        _l("Коды"),
        validators=[
            DataRequired(REQUIRED),
            Length(2, 20, message=LENGTH_MSG),
            Regexp(r"^[A-Z0-9-]+$", message=_l("Тек бас латын әріптері, сандар және «-» (мыс. ALA-01).")),
        ],
    )
    city = StringField(_l("Қала / өңір"), validators=[DataRequired(REQUIRED), Length(2, 100, message=LENGTH_MSG)])
    latitude = DecimalCommaFloatField(
        _l("Ендік"), validators=[InputRequired(REQUIRED), NumberRange(-90, 90, _l("Ендік −90…90 аралығында болуы керек."))]
    )
    longitude = DecimalCommaFloatField(
        _l("Бойлық"),
        validators=[InputRequired(REQUIRED), NumberRange(-180, 180, _l("Бойлық −180…180 аралығында болуы керек."))],
    )
    elevation = DecimalCommaFloatField(
        _l("Биіктік (м)"), validators=[Optional(), NumberRange(-500, 9000, _l("Биіктік −500…9000 м аралығында болуы керек."))]
    )
    phone = StringField(
        _l("Телефон"),
        validators=[Optional(), Regexp(PHONE_RE, message=_l("Телефон форматы дұрыс емес (мыс. +7 727 123 45 67)."))],
    )
    email = StringField("Email", validators=[Optional(), Email(message=_l("Email адресі дұрыс емес.")), Length(max=120, message=MAX_LENGTH_MSG)])
    description = TextAreaField(_l("Сипаттама"), validators=[Optional(), Length(max=1000, message=MAX_LENGTH_MSG)])
    parameter_ids = MultiCheckboxField(_l("Өлшенетін параметрлер"), coerce=int)
    is_active = BooleanField(_l("Белсенді станция"), default=True)
    photo_file = FileField(
        _l("Фото (PNG, JPG, GIF, WEBP — 5 МБ дейін)"),
        validators=[FileAllowed(sorted(IMAGE_EXTENSIONS), _l("Тек сурет файлдары рұқсат етіледі."))],
    )
    submit = SubmitField(_l("Сақтау"))

    def __init__(self, *args, station=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._station = station
        self.parameter_ids.choices = [
            (p.id, f"{translate_data(p.name)} ({p.unit})") for p in Parameter.query.order_by(Parameter.name)
        ]

    def _ensure_unique(self, column, value, message):
        query = Station.query.filter(func.lower(column) == value.strip().lower())
        if self._station is not None:
            query = query.filter(Station.id != self._station.id)
        if query.first():
            raise ValidationError(message)

    def validate_name(self, field):
        self._ensure_unique(Station.name, field.data, _l("Бұл атаумен станция бұрыннан бар."))

    def validate_code(self, field):
        self._ensure_unique(Station.code, field.data, _l("Бұл кодпен станция бұрыннан бар."))


class ParameterForm(FlaskForm):
    name = StringField(_l("Атауы"), validators=[DataRequired(REQUIRED), Length(2, 60, message=LENGTH_MSG)])
    code = StringField(
        _l("Коды (латынша)"),
        validators=[
            DataRequired(REQUIRED),
            Length(2, 30, message=LENGTH_MSG),
            Regexp(r"^[a-z][a-z0-9_]*$", message=_l("Кіші латын әріптері, сандар және «_» (мыс. wind_speed).")),
        ],
    )
    unit = StringField(_l("Өлшем бірлігі"), validators=[DataRequired(REQUIRED), Length(1, 20, message=LENGTH_MSG)])
    min_value = DecimalCommaFloatField(_l("Ең кіші рұқсат мән"), validators=[InputRequired(REQUIRED)])
    max_value = DecimalCommaFloatField(_l("Ең үлкен рұқсат мән"), validators=[InputRequired(REQUIRED)])
    description = TextAreaField(_l("Сипаттама"), validators=[Optional(), Length(max=500, message=MAX_LENGTH_MSG)])
    submit = SubmitField(_l("Сақтау"))

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
        self._ensure_unique(Parameter.name, field.data, _l("Бұл атаумен параметр бар."))

    def validate_code(self, field):
        self._ensure_unique(Parameter.code, field.data, _l("Бұл кодпен параметр бар."))

    def validate_max_value(self, field):
        if self.min_value.data is not None and field.data is not None and field.data <= self.min_value.data:
            raise ValidationError(_l("Ең үлкен мән ең кіші мәннен үлкен болуы керек."))


class ObservationForm(FlaskForm):
    station_id = SelectField(_l("Станция"), coerce=int, validators=[InputRequired(REQUIRED)])
    parameter_id = SelectField(_l("Параметр"), coerce=int, validators=[InputRequired(REQUIRED)])
    value = DecimalCommaFloatField(_l("Мәні"), validators=[InputRequired(REQUIRED)])
    observed_at = DateTimeLocalField(
        _l("Бақылау уақыты"), format="%Y-%m-%dT%H:%M", validators=[InputRequired(REQUIRED)]
    )
    note = TextAreaField(_l("Ескертпе"), validators=[Optional(), Length(max=500, message=_l("Ең көбі 500 таңба."))])
    attachment_file = FileField(
        _l("Тіркеме (PDF, PNG, JPG, CSV, TXT — 5 МБ дейін)"),
        validators=[FileAllowed(sorted(DOCUMENT_EXTENSIONS), _l("Бұл файл түріне рұқсат жоқ."))],
    )
    submit = SubmitField(_l("Сақтау"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.station_id.choices = [
            (s.id, translate_data(s.name) if s.is_active else _("{name} (белсенді емес)", name=translate_data(s.name)))
            for s in Station.query.order_by(Station.name)
        ]
        self.parameter_id.choices = [
            (p.id, f"{translate_data(p.name)}, {p.unit}") for p in Parameter.query.order_by(Parameter.name)
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

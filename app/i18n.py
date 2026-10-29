"""Қарапайым көптілділік: қазақша (әдепкі) және орысша.

Түпнұсқа мәтін — қазақша, ол сөздіктің кілті болады. Орысша аудармалары
`translations_ru.py` ішінде. Таңдалған тіл сессияда сақталады.
"""
from flask import has_request_context, session

from .translations_ru import RU

LANGUAGES = {"kk": "Қазақша", "ru": "Русский"}
DEFAULT_LANGUAGE = "kk"


def get_locale():
    if has_request_context():
        lang = session.get("lang")
        if lang in LANGUAGES:
            return lang
    return DEFAULT_LANGUAGE


def gettext(text, **kwargs):
    """Мәтінді ағымдағы тілге аударады; {name} орындарына мәндер қойылады."""
    text = str(text)
    if get_locale() == "ru":
        text = RU.get(text, text)
    return text.format(**kwargs) if kwargs else text


def translate_data(value):
    """Дерекқордағы мәтін (станция, параметр атауы т.б.) — аудармасы болса ғана ауыстырылады."""
    if value is None:
        return value
    return RU.get(value, value) if get_locale() == "ru" else value


class LazyString:
    """Модуль деңгейінде (формалар, сорттау тізімі) жарияланып, сұраныс кезінде аударылатын мәтін."""

    def __init__(self, text, kwargs):
        self._text = text
        self._kwargs = kwargs

    def __str__(self):
        return gettext(self._text, **self._kwargs)

    def __repr__(self):
        return f"LazyString({self._text!r})"

    def __mod__(self, other):
        # WTForms кей валидаторлары хабарламаны `message % dict(...)` түрінде пішімдейді
        return str(self) % other

    def __add__(self, other):
        return str(self) + str(other)

    def __radd__(self, other):
        return str(other) + str(self)

    def __len__(self):
        return len(str(self))

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(self._text)


def lazy_gettext(text, **kwargs):
    return LazyString(text, kwargs)

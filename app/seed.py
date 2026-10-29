"""Демо деректер: Қазақстан станциялары және соңғы N күндегі бақылаулар."""
import math
import random
from datetime import date, datetime, time, timedelta

from . import db
from .models import ROLE_ADMIN, ROLE_USER, Observation, Parameter, Station, User

USERS = [
    ("admin", "admin@weatherlog.kz", "admin123", ROLE_ADMIN),
    ("user", "user@weatherlog.kz", "user123", ROLE_USER),
    ("aigerim", "aigerim@weatherlog.kz", "aigerim123", ROLE_USER),
]

# атауы, коды, өлшем бірлігі, мин, макс, сипаттама
PARAMETERS = [
    ("Температура", "temperature", "°C", -60, 60, "Жер бетінен 2 м биіктіктегі ауа температурасы."),
    ("Салыстырмалы ылғалдылық", "humidity", "%", 0, 100, "Ауадағы су буының қанығу дәрежесі."),
    ("Атмосфералық қысым", "pressure", "гПа", 870, 1085, "Теңіз деңгейіне келтірілген қысым."),
    ("Жел жылдамдығы", "wind_speed", "м/с", 0, 75, "10 м биіктіктегі орташа жел жылдамдығы."),
    ("Жауын-шашын", "precipitation", "мм", 0, 500, "Соңғы 12 сағаттағы жауын-шашын мөлшері."),
]

# атауы, коды, қала, ендік, бойлық, биіктік, телефон, орташа t°, параметр кодтары, сипаттама
STATIONS = [
    ("Алматы метеостанциясы", "ALA-01", "Алматы", 43.2389, 76.8897, 848, "+7 727 255 00 01", 9.5, None,
     "Іле Алатауының етегіндегі қалалық станция."),
    ("Медеу тау станциясы", "MED-01", "Алматы", 43.1570, 77.0590, 1691, "+7 727 255 00 02", 4.0,
     ["temperature", "humidity", "wind_speed", "precipitation"], "Медеу шатқалындағы биік тау бекеті."),
    ("Астана метеостанциясы", "AST-01", "Астана", 51.1694, 71.4491, 347, "+7 7172 55 10 10", 3.0, None,
     "Елорданың негізгі синоптикалық станциясы."),
    ("Шымкент метеостанциясы", "SHY-01", "Шымкент", 42.3417, 69.5901, 506, "+7 7252 53 20 20", 13.0, None,
     "Оңтүстік өңірдің тірек станциясы."),
    ("Ақтау метеостанциясы", "AKT-01", "Ақтау", 43.6511, 51.1979, 15, "+7 7292 30 40 40", 14.0, None,
     "Каспий жағалауындағы теңіз станциясы."),
    ("Өскемен метеостанциясы", "UKK-01", "Өскемен", 49.9483, 82.6275, 286, "+7 7232 70 50 50", 4.5, None,
     "Шығыс Қазақстандағы Ертіс бойындағы станция."),
    ("Бурабай станциясы", "BUR-01", "Ақмола облысы", 53.0830, 70.3000, 320, None, 2.5,
     ["temperature", "humidity", "precipitation"], "Бурабай ұлттық паркіндегі автоматты бекет."),
]

NOTES = ["Ашық аспан", "Бұлтты", "Бұлтты, кей жерде ашық", "Тұман", "Жеңіл жаңбыр", "Қатты жел",
         "Қар аралас жаңбыр", "Таңертеңгі қырау", "Тұманды, көріну нашар"]
HOURS = (7, 13, 19)


def seed_demo_data(days=30, rng_seed=42):
    rng = random.Random(rng_seed)

    users = []
    for username, email, password, role in USERS:
        user = User(username=username, email=email, role=role)
        user.set_password(password)
        users.append(user)
    db.session.add_all(users)

    params = {}
    for name, code, unit, vmin, vmax, desc in PARAMETERS:
        params[code] = Parameter(name=name, code=code, unit=unit, min_value=vmin, max_value=vmax, description=desc)
    db.session.add_all(params.values())

    stations = []
    for name, code, city, lat, lon, elev, phone, base_t, codes, desc in STATIONS:
        station = Station(
            name=name, code=code, city=city, latitude=lat, longitude=lon, elevation=elev, phone=phone,
            email=f"{code.lower()}@weatherlog.kz", description=desc,
            parameters=[params[c] for c in (codes or params)],
        )
        station.base_temp = base_t
        stations.append(station)
    db.session.add_all(stations)
    db.session.flush()

    observations = []
    today = date.today()
    now = datetime.now()
    for station in stations:
        drift = 0.0          # синоптикалық ауытқу (бірнеше күнге созылатын)
        pressure = 1016.0
        codes = {p.code for p in station.parameters}
        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            drift = 0.7 * drift + rng.gauss(0, 1.8)
            pressure = 1016 + 0.8 * (pressure - 1016) + rng.gauss(0, 3.5)
            seasonal = station.base_temp + 0.22 * (offset - days / 2)  # күз: күн сайын біртіндеп суыну
            rainy_day = rng.random() < 0.3
            for hour in HOURS:
                observed_at = datetime.combine(day, time(hour, rng.choice((0, 0, 10, 20, 30))))
                if observed_at > now:
                    continue
                diurnal = 4.5 * math.sin((hour - 9) / 24 * 2 * math.pi)
                temp = seasonal + drift + diurnal + rng.gauss(0, 0.8)
                values = {
                    "temperature": round(temp, 1),
                    "humidity": round(min(98, max(18, 72 - 1.6 * diurnal - 1.2 * drift + (15 if rainy_day else 0)
                                                  + rng.gauss(0, 5))), 0),
                    "pressure": round(pressure - (4 if rainy_day else 0) + rng.gauss(0, 0.8), 1),
                    "wind_speed": round(max(0.0, rng.gammavariate(2.0, 1.6) + (2 if rainy_day else 0)), 1),
                    "precipitation": round(rng.uniform(0.2, 7.5), 1) if rainy_day and rng.random() < 0.6 else 0.0,
                }
                note = rng.choice(NOTES) if rng.random() < 0.12 else None
                author = rng.choice(users)
                for code in codes:
                    observations.append(Observation(
                        station_id=station.id, parameter_id=params[code].id, user_id=author.id,
                        value=values[code], observed_at=observed_at, note=note,
                    ))
    db.session.add_all(observations)
    db.session.commit()
    return {"users": len(users), "stations": len(stations), "parameters": len(params), "observations": len(observations)}

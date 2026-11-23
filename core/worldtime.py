# -*- coding: utf-8 -*-
"""core/worldtime.py — ВРЕМЯ В ГОРОДЕ (Ф27, 23.11): «время в Токио».

Час Создателя — Европа/Москва, а друзья и серверы живут в других
поясах. zoneinfo — главный источник; российские города имеют честный
фоллбэк (страна не переводит часы с 2014 — постоянный сдвиг), для
остальных при недоступной базе поясов — честный отказ, не выдумка
(закон фактов: дом не придумывает сдвиги).
"""
from __future__ import annotations

import datetime as dt

CITIES = {
    "москва": ("Europe/Moscow", 3),
    "спб": ("Europe/Moscow", 3),
    "питер": ("Europe/Moscow", 3),
    "санкт-петербург": ("Europe/Moscow", 3),
    "калининград": ("Europe/Kaliningrad", 2),
    "екатеринбург": ("Asia/Yekaterinburg", 5),
    "новосибирск": ("Asia/Novosibirsk", 7),
    "красноярск": ("Asia/Krasnoyarsk", 7),
    "иркутск": ("Asia/Irkutsk", 8),
    "владивосток": ("Asia/Vladivostok", 11),
    "токио": ("Asia/Tokyo", None),
    "пекин": ("Asia/Shanghai", None),
    "дубай": ("Asia/Dubai", None),
    "лондон": ("Europe/London", None),
    "париж": ("Europe/Paris", None),
    "берлин": ("Europe/Berlin", None),
    "нью-йорк": ("America/New_York", None),
    "лос-анджелес": ("America/Los_Angeles", None),
}
RU_CITIES = {"москва", "спб", "питер", "санкт-петербург", "калининград",
             "екатеринбург", "новосибирск", "красноярск", "иркутск",
             "владивосток"}


def time_in(city: str, now: dt.datetime = None) -> str:
    """«время в Токио» — часы города; фоллбэки честные."""
    now = now or dt.datetime.now(dt.timezone.utc)
    key = str(city or "").strip().lower()
    if key not in CITIES:
        return ("города «%s» не знаю; умею: %s — скажи «время в Токио»"
                % (str(city or "")[:40], ", ".join(sorted(set(
                    k for k in CITIES if "-" not in k and len(k) > 2))[:10])))
    zone_name, ru_shift = CITIES[key]
    try:
        from zoneinfo import ZoneInfo
        local = (now if now.tzinfo else now.replace(tzinfo=dt.timezone.utc)) \
            .astimezone(ZoneInfo(zone_name))
        return "%s сейчас %s (%s)" % (
            _city_phrase(key), local.strftime("%H:%M"), zone_name)
    except Exception:
        if ru_shift is not None:
            local = (now if now.tzinfo
                     else now.replace(tzinfo=dt.timezone.utc)) \
                .astimezone(dt.timezone(dt.timedelta(hours=ru_shift)))
            return ("%s сейчас %s (постоянный сдвиг UTC+%d — Россия "
                    "не переводит часы)" % (_city_phrase(key),
                                            local.strftime("%H:%M"),
                                            ru_shift))
        return ("часовой пояс %s недоступен (нет базы tzdata — скажи "
                "архитектору), а выдумывать сдвиг не буду" % zone_name)


_PHRASES = {
    "москва": "в Москве", "спб": "в Питере", "питер": "в Питере",
    "санкт-петербург": "в Санкт-Петербурге",
    "калининград": "в Калининграде", "екатеринбург": "в Екатеринбурге",
    "новосибирск": "в Новосибирске", "красноярск": "в Красноярске",
    "иркутск": "в Иркутске", "владивосток": "во Владивостоке",
    "токио": "в Токио", "пекин": "в Пекине", "дубай": "в Дубае",
    "лондон": "в Лондоне", "париж": "в Париже", "берлин": "в Берлине",
    "нью-йорк": "в Нью-Йорке", "лос-анджелес": "в Лос-Анджелесе",
}


def _city_phrase(key: str) -> str:
    """Город в предложном падеже с верным предлогом — русский честный."""
    return _PHRASES.get(key, "в %s" % key)

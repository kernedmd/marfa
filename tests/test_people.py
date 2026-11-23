# -*- coding: utf-8 -*-
"""Тесты круга «знакомство» (Ф2, 23.11): дом знает, как тебя зовут."""
import json
from pathlib import Path

import pytest

from core import config, people


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    yield tmp_path


# ---------- файл знакомства ----------

def test_set_and_get_name(home):
    r = people.set_name("илья")
    assert "Илья" in r                     # регистр по-человечески
    assert people.get_name() == "Илья"
    assert people.met_on()                 # дата встречи записана


def test_set_name_remembered_in_rag(home):
    saved = []
    mem = type("M", (), {"remember": staticmethod(
        lambda text, tags=None, importance=0.0: saved.append((text, tags)))})()
    people.set_name("Мария", memory=mem)
    assert saved and "Мария" in saved[0][0] and "знакомство" in saved[0][1]


def test_set_name_garbage_rejected(home):
    r = people.set_name("12345")
    assert "не похоже на имя" in r
    assert people.get_name() is None


def test_set_name_updates_not_duplicates(home):
    people.set_name("Илья")
    r = people.set_name("Ильдар")
    assert "было Илья" in r
    assert people.get_name() == "Ильдар"


def test_rename_survives_broken_rag(home):
    class Boom:
        def remember(self, *a, **kw):
            raise RuntimeError("база спит")

    r = people.set_name("Илья", memory=Boom())
    assert "Илья" in r and people.get_name() == "Илья"


def test_forget_name_honest(home):
    people.set_name("Илья")
    r = people.forget_name()
    assert "забыла" in r and people.get_name() is None
    assert "не было" in people.forget_name()   # второй раз — честно


def test_broken_file_is_not_crash(home):
    (Path(config.DATA_DIR)).mkdir(parents=True, exist_ok=True)
    people.people_file().write_text("не json совсем", encoding="utf-8")
    assert people.get_name() is None
    r = people.who_am_i()
    assert "не знаю" in r


# ---------- «кто я»: имя + зрительная память + воспоминания ----------

def test_who_am_i_without_anything_is_honest(home):
    r = people.who_am_i()
    assert "не знаю" in r and "меня зовут" in r


def test_who_am_i_full_picture(home):
    people.set_name("Илья")
    r = people.who_am_i(eyes_face="Мужчина в полосатой футболке")
    assert "Илья" in r and "знакомы" in r
    assert "полосатой футболке" in r

# -*- coding: utf-8 -*-
r"""tests/test_sync_button.py — статические проверки кнопки 80_sync_github.bat.

Кнопка работает на Z440 (cmd.exe), на станции не запускается — поэтому
проверяем текст файла. Урок первого прогона (19.11.2026, ночь): bundle
скачался, но не влился, а кнопка v2.1 замаскировала сбой и продолжила
пушить. v2.2 не имеет права повторять это — что и фиксируют тесты.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "scripts" / "80_sync_github.bat"


def _text() -> str:
    return BAT.read_text(encoding="utf-8")


def test_button_exists():
    assert BAT.is_file(), "кнопка scripts/80_sync_github.bat пропала"


def test_dirty_tree_committed_before_merges():
    """Грязь коммитится ДО слияний — merge не откажется поверх фантомных правок."""
    t = _text()
    assert ":clean_tree" in t
    assert "локальные правки перед слиянием" in t
    # чистка дерева вызывается и перед GitHub-слиянием, и перед приёмом bundle
    assert t.count("call :clean_tree") >= 2


def test_failures_still_honest():
    """То, что автомат не осилил — честная остановка, а не маскировка."""
    t = _text()
    assert "git merge --abort" in t
    assert t.count("покажи архитектору") >= 2  # усыновление и авторазрешение
    # старый маскирующий фолбэк удалён
    assert "(завершение)" not in t


def test_adoption_for_unrelated_histories():
    """Несвязанные истории — усыновление автоматом (v3.0).

    Урок второго прогона: дом/GitHub/станция — три несвязанные линии,
    каждый общий файл = add/add, который -X theirs не решает.
    """
    t = _text()
    assert "git merge-base HEAD FETCH_HEAD" in t  # связность проверяется ДО слияния
    assert "усыновление" in t
    assert "git merge --no-commit --allow-unrelated-histories FETCH_HEAD" in t
    assert "git checkout FETCH_HEAD -- ." in t   # дерево архитектора целиком


def test_related_conflicts_autoresolved():
    """Конфликт при общей истории — «архитектор сильнее» без ручного труда."""
    t = _text()
    assert "git checkout --theirs -- ." in t
    assert "авторазрешение" in t
    # внутри :import_bundle порядок: «уже вросла» -> усыновление -> авторазрешение
    sub = t[t.index(":import_bundle"):]
    assert sub.index("уже вросла") < sub.index("усыновление") < sub.index("авторазрешение")


def test_sentinel_after_import():
    """После приёма bundle код архитектора обязан доехать — иначе честный сбой."""
    t = _text()
    assert "IMPORTED" in t
    assert "не доехал" in t


def test_push_failure_not_fatal():
    """Провал пуша в GitHub — предупреждение, петля (bundle) продолжается."""
    t = _text()
    assert "Пуш не прошёл" in t
    # после предупреждения о пуше кнопка продолжает собирать bundle
    assert t.index("Пуш не прошёл") < t.index("git bundle create")


def test_heavy_llama_builds_out_of_git():
    """Сборки llama-cuda/llama-vulkan — рантайм: в игноре и выводятся из git."""
    t = _text()
    assert "llama-cuda/" in t and "llama-vulkan/" in t  # .gitignore кнопкой
    assert "git rm -r -q --cached llama-cuda llama-vulkan" in t


def test_self_update_via_temp_copy():
    """Кнопка работает с временной копии — петля может обновить её саму."""
    t = _text()
    assert "MARFA_SYNC_RELAUNCH" in t
    assert "%TEMP%\\marfa_sync_run.bat" in t


def test_fat_history_surgery():
    """История толще 100 МБ — пересборка автоматом (v3.1).

    Урок третьего прогона: тяжёлые сборки llama застряли в истории
    первого снимка; rm --cached чистит только будущее, пуш падает,
    bundle не пролезает в чат.
    """
    t = _text()
    assert "git count-objects -v" in t            # измерение толщины истории
    assert "GTR 102400" in t                      # порог: 100 МБ
    assert "call :surgery" in t and "\n:surgery" in t
    assert "Move-Item -LiteralPath .git" in t     # старая история -> .git_old\
    assert ".git_old/" in t                       # и в игнор-списке кнопки
    # пересборка не тянет старую историю с GitHub: пуш с заменой
    assert "git push --force origin main" in t
    assert 'if "%SURGERY%"=="1" (' in t           # флаг разведён по шагам
    # ничего не удаляется насовсем — старая история сохранена
    assert "можно удалить через неделю" in t

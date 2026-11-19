# Доставка коммитов в GitHub — github.com/kernedmd/marfa (правило 0.2)

Репозиторий собирается через **git bundle**: один файл содержит всю историю коммитов.
Пуш выполняется с машины, где есть авторизация (SSH-ключ или PAT — Раздел 2.4 ТЗ).
Токены в чат не передавать никогда: СТРАЖ Ф105 и гигиена 2.4 против.

> **Актуальный bundle: 12.11.2026 (вечер), 20 коммитов (tip 17d57c6 — «РУЧНОЙ РЕЖИМ 12.11.2026 — светофор 90_manual_check + зеркала pip/torch/HF»).**
> Ручной режим («всё руками»): светофор `scripts\90_manual_check.bat` ничего не качает —
> показывает, что есть в доме, а для каждой недостающей позиции печатает ссылку, имя файла
> и место. Python, если уже стоит на машине, шаг 01 подключает сам; скачанное в
> `downloads\` и `models\` конвейер подхватывает сам; pip при провале pypi.org повторяет
> через зеркало tuna; torch — колёса cu118 с aliyun; студент — hf-mirror.com.
> Если старый bundle уже запушен — берите Вариант А (fetch+merge).

## Вариант А: поверх существующего репозитория (рекомендуется)

На Z440 (или любой машине с клоном `marfa`):

```bat
cd C:\Marfa
git fetch origin main

:: показать, что принесёт bundle (безопасно, ничего не меняет)
git bundle verify marfa.bundle
git log --oneline origin/main..FETCH_HEAD   :: после шага fetch из bundle

:: принять историю
git fetch marfa.bundle main:bundle-main
git checkout main
git merge bundle-main --no-edit
:: при конфликте: ours=ваш origin/main, theirs=bundle; менять ТЗ-файлы нельзя (docs/MASTER_TZ_v9_3.md)

git push origin main
```

## Если git на Z440 вообще не установлен ('git' не является командой)

```bat
scripts\05_install_git.bat
:: поставит портативный git в C:\Marfa  ools\git (ничего в Program Files)
:: и напечатает готовый блок команд: init -> fetch bundle -> reset --hard -> push
```

`git reset --hard bundle-main` одновременно обновит все скрипты дома до последней
версии bundle; data\, models\, downloads\, logs\ он не трогает — они в .gitignore.

## Вариант B: если репозиторий на GitHub пуст или пересоздаётся

```bat
git clone marfa.bundle marfa-push
cd marfa-push
git checkout main
git remote set-url origin https://github.com/kernedmd/marfa.git
git push origin main
```

## Авторизация (Раздел 2.4 ТЗ)

- Постоянно: **SSH-ключ на Z440** (рекомендация ТЗ): `ssh-keygen -t ed25519`,
  публичный ключ добавить в GitHub → Settings → SSH keys.
- Разово: **fine-grained PAT** с правом только `Contents: Read and write`,
  минимальный срок, отозвать сразу после пуша.
- Пароли GitHub не принимает; `.env` и ключи в репозиторий не попадают (2.4).

## После пуша — проверка (по духу 6.6)

```bat
git log --oneline -15
git status                      :: чисто, ничего не забыто
git ls-files                    :: .env, models/, venv/, logs/, data/ — ОТСУТСТВУЮТ
scripts\verify.bat              :: пункт «.env не в git» должен быть [ОК]
```

Дисциплина дальше: каждая фишка — отдельный коммит (Раздел 5), откат — `git revert`, не «починю потом» (6.7).

## Сервер архитектора с прямым доступом (опция, 17.11.2026)

Если сервер архитектора должен забирать репозиторий сам, без пересылки bundle
через чат: fine-grained PAT с правом **Contents: Read-only** кладётся Создателем
в `.env` на сервере (`MARFA_GH_TOKEN=...`), и `scripts/server_sync.py` v1.2
делает fetch + merge прямо из GitHub. Токен не в чат, не в логи, не в
`.git/config`. Пуш станции в GitHub — опция `MARFA_GH_PUSH=1`, по умолчанию
выключена. Подробности и гарантии: docs/SYNC_PROTOCOL_v1.md, раздел 4а.

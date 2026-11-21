# -*- coding: utf-8 -*-
"""markdown_render.py — безопасный Markdown -> HTML для ответов Марфы (№12).

Мозг отвечает списками, кодом и заголовками — в чате как textContent это
каша. Здесь крошечное подмножество Markdown, РЕНДЕР НА СЕРВЕРЕ:
сначала ВЕСЬ текст экранируется (XSS-гигиена №12), потом разметка.
Панель получает готовый безопасный HTML и не доверяет мозгу ни байтом.

Поддержка (вне код-блоков):
  ``` fenced блоки ```     — дословно, без разметки внутри
  `инлайн-код`             — <code>
  **жирный**, *курсив*     — <b>, <i>
  # ## ### заголовки       — <h3> <h4> <h5> (крупнее — не для чата)
  - пункт / 1. пункт       — <ul> <ol> (подряд идущие строки)
  [текст](https://...)     — <a>, только http(s): javascript: и прочее
                             остаются текстом (гигиена)
  пустая строка            — граница абзаца; внутри абзаца \\n -> <br>
"""
from __future__ import annotations

import html as _html
import re

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")
_ITAL_RE = re.compile(r"\*([^*\n]+)\*")
_CODE_RE = re.compile(r"`([^`\n]+)`")
_H_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_UL_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_OL_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")


def _inline(s: str) -> str:
    """Инлайн-разметка одной строки (уже экранированной)."""
    s = _CODE_RE.sub(r"<code>\1</code>", s)
    s = _BOLD_RE.sub(r"<b>\1</b>", s)
    s = _ITAL_RE.sub(r"<i>\1</i>", s)

    def _link(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        if re.match(r"^https?://", url, re.IGNORECASE):
            return '<a href="%s" target="_blank" rel="noopener">%s</a>' % (url, label)
        return m.group(0)          # не-http «ссылка» — просто текст (гигиена)

    return _LINK_RE.sub(_link, s)


def to_safe_html(text: str) -> str:
    """Markdown -> безопасный HTML. Вход пустой — честный пустой выход."""
    if not text:
        return ""
    # 1) экранируем ВСЁ до любой разметки — теги из ответа мозга мертвы
    lines = _html.escape(text, quote=True).split("\n")

    out: list[str] = []
    para: list[str] = []
    code: list[str] | None = None
    list_tag: str | None = None     # открытый "ul"/"ol" или None

    def flush_para() -> None:
        nonlocal para
        if para:
            out.append("<p>" + "<br>".join(_inline(l) for l in para) + "</p>")
            para = []

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            out.append("</%s>" % list_tag)
            list_tag = None

    for raw in lines:
        # --- fenced code: дословно, разметка внутри не работает ---
        if raw.strip().startswith("```"):
            if code is None:
                flush_para()
                close_list()
                code = []
            else:
                out.append("<pre><code>" + "\n".join(code) + "</code></pre>")
                code = None
            continue
        if code is not None:
            code.append(raw)
            continue

        stripped = raw.strip()
        if not stripped:                       # пустая строка — границы блоков
            flush_para()
            close_list()
            continue

        m = _H_RE.match(stripped)
        if m and not list_tag:
            flush_para()
            level = len(m.group(1)) + 2        # # -> h3, ## -> h4, ### -> h5
            out.append("<h%d>%s</h%d>" % (level, _inline(m.group(2).strip()), level))
            continue

        m = _UL_RE.match(raw)
        if m:
            flush_para()
            if list_tag != "ul":
                close_list()
                out.append("<ul>")
                list_tag = "ul"
            out.append("<li>%s</li>" % _inline(m.group(1).strip()))
            continue

        m = _OL_RE.match(raw)
        if m:
            flush_para()
            if list_tag != "ol":
                close_list()
                out.append("<ol>")
                list_tag = "ol"
            out.append("<li>%s</li>" % _inline(m.group(1).strip()))
            continue

        close_list()
        para.append(raw)

    if code is not None:                       # незакрытый блок — не терять
        out.append("<pre><code>" + "\n".join(code) + "</code></pre>")
    flush_para()
    close_list()
    return "".join(out)

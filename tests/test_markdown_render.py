# -*- coding: utf-8 -*-
r"""tests/test_markdown_render.py — безопасный Markdown для ответов Марфы (№12).

Правило №12 из роадмапа-30: подсветка кода, списки, заголовки — и
XSS-гигиена (экранирование). Рендер на сервере: сначала экранируется
ВЕСЬ текст, потом разметка — теги из ответа мозга мертвы по построению.
"""
from web.markdown_render import to_safe_html


# ---------- разметка ----------

def test_bold_italic_code():
    assert to_safe_html("**жирный**") == "<p><b>жирный</b></p>"
    assert to_safe_html("*курсив*") == "<p><i>курсив</i></p>"
    assert to_safe_html("код `x = 1` вот") == "<p>код <code>x = 1</code> вот</p>"


def test_fenced_code_block_verbatim():
    out = to_safe_html("вот код:\n```\n**не жирный** <b>и не тег</b>\n```")
    assert "<pre><code>" in out
    assert "**не жирный**" in out          # разметка внутри кода не работает
    assert "&lt;b&gt;и не тег&lt;/b&gt;" in out


def test_unclosed_fence_not_lost():
    out = to_safe_html("```\nхвост без закрывающих")
    assert "хвост без закрывающих" in out and "<pre><code>" in out


def test_headers():
    assert to_safe_html("# Заголовок") == "<h3>Заголовок</h3>"
    assert to_safe_html("## Два") == "<h4>Два</h4>"
    assert to_safe_html("### Три") == "<h5>Три</h5>"


def test_lists():
    out = to_safe_html("- один\n- два")
    assert out == "<ul><li>один</li><li>два</li></ul>"
    out = to_safe_html("1. первый\n2. второй")
    assert out == "<ol><li>первый</li><li>второй</li></ol>"


def test_paragraphs_and_br():
    out = to_safe_html("строка одна\nстрока две\n\nновый абзац")
    assert out == "<p>строка одна<br>строка две</p><p>новый абзац</p>"


def test_http_link_ok_javascript_not_linked():
    out = to_safe_html("[дом](https://github.com/kernedmd/marfa)")
    assert '<a href="https://github.com/kernedmd/marfa"' in out
    # javascript: остаётся текстом — гигиена №12
    out = to_safe_html("[жми](javascript:alert(1))")
    assert "<a " not in out
    assert "javascript:alert(1)" in out


def test_empty_is_empty():
    assert to_safe_html("") == ""


# ---------- XSS-гигиена ----------

def test_script_tag_neutralized():
    out = to_safe_html("<script>alert(1)</script>")
    assert "<script" not in out
    assert "&lt;script&gt;" in out


def test_img_onerror_neutralized():
    out = to_safe_html('<img src=x onerror=alert(1)>')
    assert "<img" not in out
    assert "&lt;img src=x onerror=alert(1)&gt;" in out


def test_event_handler_in_markdown_link_label():
    out = to_safe_html("[<b onclick=x>](https://ok.example)")
    assert "<b onclick" not in out               # метка экранирована до разметки


def test_quote_escaped_in_attributes():
    out = to_safe_html('```\n"a"\n```')
    assert "&quot;a&quot;" in out


def test_plain_math_readable():
    out = to_safe_html("если a < b и c > d")
    assert "a &lt; b" in out and "c &gt; d" in out

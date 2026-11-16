"""Default presentation layer for HTML notifications.

MeoW renders ``msgType=html`` inside the app, where a bare HTML snippet
inherits a very small base font and looks unreadable on a phone. Rather than
asking every caller to hand-write CSS, ``--html`` wraps the snippet in a
container that carries a large inline ``font-size`` (inline styles survive
sanitizers that drop ``<style>``) plus a class-scoped stylesheet for headings,
lists, code and tables.

Two field-tested details are baked in:

* the container has an explicit pixel ``width`` (900px) with ``max-width:100%``
  so text wraps at ~18 CJK characters per line instead of overflowing;
* the ``<style>`` block trails the content, because MeoW derives the collapsed
  notification preview from the head of the message and a leading stylesheet
  made that preview blank.

Deliberate limits:

* no ``color`` / ``background`` — the app's light or dark theme keeps working;
* no external fonts, scripts or images — nothing to fail offline;
* everything can be overridden: ``font_size``, ``width``, ``extra_css`` or
  ``wrap=False``.
"""

from __future__ import annotations

from typing import Optional

from .constants import DEFAULT_HTML_FONT_SIZE, DEFAULT_HTML_WIDTH

#: Comfortable size on a phone; ~4.8x what a bare snippet renders at.
DEFAULT_FONT_SIZE = DEFAULT_HTML_FONT_SIZE
DEFAULT_WIDTH = DEFAULT_HTML_WIDTH
BASE_LINE_HEIGHT = 1.55

#: Height (px) assumed to be "about five lines" when the caller passes none.
HEIGHT_LINES = 5
MIN_HEIGHT = 200

_CLASS = "meow-html-push"

_BASE_CSS = """\
.__CLASS__ { font-size: __FONT_PX__px; line-height: __LINE_HEIGHT__; word-wrap: break-word; overflow-wrap: anywhere; }
.__CLASS__ p { margin: 0 0 0.55em; }
.__CLASS__ p:last-child { margin-bottom: 0; }
.__CLASS__ h1 { font-size: 1.5em; line-height: 1.3; margin: 0.3em 0 0.4em; font-weight: 700; }
.__CLASS__ h2 { font-size: 1.32em; line-height: 1.32; margin: 0.3em 0 0.4em; font-weight: 700; }
.__CLASS__ h3 { font-size: 1.16em; line-height: 1.35; margin: 0.3em 0 0.35em; font-weight: 600; }
.__CLASS__ h4, .__CLASS__ h5, .__CLASS__ h6 { font-size: 1.05em; margin: 0.3em 0; font-weight: 600; }
.__CLASS__ ul, .__CLASS__ ol { margin: 0 0 0.55em; padding-left: 1.15em; }
.__CLASS__ li { margin: 0.15em 0; }
.__CLASS__ img { max-width: 100%; height: auto; }
.__CLASS__ a { text-decoration: underline; }
.__CLASS__ code, .__CLASS__ pre { font-family: monospace; font-size: 0.9em; white-space: pre-wrap; word-break: break-all; }
.__CLASS__ blockquote { margin: 0.4em 0; padding-left: 0.6em; border-left: 4px solid rgba(128, 128, 128, 0.45); }
.__CLASS__ small { font-size: 0.85em; }
.__CLASS__ table { border-collapse: collapse; width: 100%; }
.__CLASS__ th, .__CLASS__ td { border: 1px solid rgba(128, 128, 128, 0.45); padding: 0.3em 0.45em; text-align: left; }
"""


def base_css(font_size: int) -> str:
    return (
        _BASE_CSS.replace("__CLASS__", _CLASS)
        .replace("__FONT_PX__", str(font_size))
        .replace("__LINE_HEIGHT__", str(BASE_LINE_HEIGHT))
    )


def default_height(font_size: int) -> int:
    """Rough card height that fits ~5 lines at *font_size*."""
    raw = font_size * BASE_LINE_HEIGHT * HEIGHT_LINES
    return max(MIN_HEIGHT, int(round(raw / 10.0)) * 10)


def is_full_document(content: str) -> bool:
    """True for complete HTML documents, which must not be wrapped again."""
    head = content.lstrip()[:512].lower()
    return head.startswith("<!doctype") or "<html" in head


def render(
    content: str,
    *,
    font_size: int = DEFAULT_FONT_SIZE,
    width: int = DEFAULT_WIDTH,
    extra_css: Optional[str] = None,
) -> str:
    """Wrap *content* with the default stylesheet and container.

    Ordering matters: the container comes **first** and the ``<style>`` block
    **last**. MeoW builds the collapsed notification preview from the leading
    characters of the message; with the stylesheet first, tag stripping left
    the preview empty. Styles still apply from any position in the document.
    """
    css = base_css(font_size)
    if extra_css and extra_css.strip():
        # Appended last: same specificity means later rules win.
        css += "\n/* --- user overrides --- */\n" + extra_css.strip() + "\n"
    style_attr = (
        "font-size:%dpx;line-height:%s;width:%dpx;max-width:100%%;"
        "box-sizing:border-box;word-wrap:break-word;overflow-wrap:anywhere;"
        % (font_size, BASE_LINE_HEIGHT, width)
    )
    return '<div class="%s" style="%s">%s</div>\n<style>\n%s</style>' % (
        _CLASS,
        style_attr,
        content,
        css,
    )


def prepare(
    content: str,
    *,
    font_size: int = DEFAULT_FONT_SIZE,
    width: int = DEFAULT_WIDTH,
    extra_css: Optional[str] = None,
    wrap: bool = True,
) -> str:
    """Apply the default styling unless disabled or already a full document."""
    if not wrap or is_full_document(content):
        return content
    return render(content, font_size=font_size, width=width, extra_css=extra_css)

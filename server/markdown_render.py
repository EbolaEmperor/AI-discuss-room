# server/markdown_render.py
import re
import markdown as _md

_md_instance = _md.Markdown(
    extensions=[
        "fenced_code",
        "tables",
        "sane_lists",
        "smarty",
    ],
    output_format="html5",
)

# Math regexes — display before inline so the longer/greedier delimiter wins.
# DOTALL on display so multi-line formulas survive. Inline forms require
# same-line content and disallow nesting another opening delimiter.
_DISPLAY_MATH_DOLLAR = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_DISPLAY_MATH_BRACKET = re.compile(r"\\\[(.+?)\\\]", re.DOTALL)
_INLINE_MATH_PAREN = re.compile(r"\\\((.+?)\\\)")
_INLINE_MATH_DOLLAR = re.compile(r"\$([^\$\n]+?)\$")


def render(text: str) -> str:
    """Render markdown.

    LaTeX delimited by ``$...$`` / ``\\(...\\)`` (inline) or ``$$...$$`` /
    ``\\[...\\]`` (display) is extracted *before* markdown processing and
    restored verbatim afterward. Without this, markdown would interpret
    characters inside the math (notably ``_`` as emphasis, ``--`` via the smarty
    extension, etc.) and corrupt the formula before client-side KaTeX gets a
    chance to render it.
    """
    if not text:
        return ""

    stash: list[str] = []

    def _hold(m: re.Match) -> str:
        idx = len(stash)
        stash.append(m.group(0))
        return f"\x00MATH{idx}\x00"

    text = _DISPLAY_MATH_DOLLAR.sub(_hold, text)
    text = _DISPLAY_MATH_BRACKET.sub(_hold, text)
    text = _INLINE_MATH_PAREN.sub(_hold, text)
    text = _INLINE_MATH_DOLLAR.sub(_hold, text)

    _md_instance.reset()
    html = _md_instance.convert(text)

    for idx, raw in enumerate(stash):
        html = html.replace(f"\x00MATH{idx}\x00", raw)
    return html

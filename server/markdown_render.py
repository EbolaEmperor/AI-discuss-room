# server/markdown_render.py
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


def render(text: str) -> str:
    """Render markdown. LaTeX delimiters ($...$, $$...$$) are left as-is for client-side KaTeX."""
    if not text:
        return ""
    _md_instance.reset()
    return _md_instance.convert(text)

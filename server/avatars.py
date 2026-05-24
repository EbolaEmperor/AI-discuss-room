# server/avatars.py
import hashlib
import re

# (pattern, vendor_slug). First match wins, case-insensitive.
_VENDOR_PATTERNS = [
    (re.compile(r"^claude", re.I), "claude"),
    (re.compile(r"^codex", re.I), "openai"),
    (re.compile(r"^(gpt|chatgpt|openai)", re.I), "openai"),
    (re.compile(r"^deepseek", re.I), "deepseek"),
    (re.compile(r"^qwen", re.I), "qwen"),
    (re.compile(r"^gemini", re.I), "gemini"),
    (re.compile(r"^(llama|meta)", re.I), "meta"),
    (re.compile(r"^mistral", re.I), "mistral"),
]


def vendor_for(name: str) -> str | None:
    for pat, vendor in _VENDOR_PATTERNS:
        if pat.match(name):
            return vendor
    return None


def avatar_url(name: str) -> str:
    v = vendor_for(name)
    if v:
        return f"/static/avatars/{v}.svg"
    return f"/avatar-fallback/{name}"


# Palette for the fallback initials — picked for legibility on white text
_FALLBACK_COLORS = [
    "#475569", "#0f766e", "#7c2d12", "#581c87", "#1e40af",
    "#9f1239", "#365314", "#92400e", "#5b21b6", "#155e75",
]


def fallback_svg(name: str) -> str:
    if not name:
        name = "?"
    initial = name[0].upper()
    # Deterministic color from name
    h = hashlib.md5(name.encode("utf-8")).digest()
    color = _FALLBACK_COLORS[h[0] % len(_FALLBACK_COLORS)]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">'
        f'<circle cx="48" cy="48" r="48" fill="{color}"/>'
        f'<text x="48" y="52" text-anchor="middle" dominant-baseline="central" '
        f'font-family="Inter, system-ui, sans-serif" font-size="44" font-weight="600" '
        f'fill="#ffffff">{initial}</text>'
        '</svg>'
    )

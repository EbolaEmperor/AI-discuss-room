# tests/test_markdown_render.py
from server.markdown_render import render


def test_underscores_inside_inline_math_preserved():
    out = render(r"see $x_1 + x_2$ here")
    assert "$x_1 + x_2$" in out
    assert "<em>" not in out


def test_underscores_inside_display_math_preserved():
    # The exact formula that was failing before the math-stash fix.
    src = (
        "$$\n"
        r"G_{\Omega_M, Y}(f) := \bigl(f(m y_j)\bigr)_{m = 0, \ldots, M}^{\,j = 1, \ldots, n}"
        "\n= "
        r"\bigl(e^{a m y_j}\bigr)_{m, j}"
        "\n"
        r"\in \mathbb{C}^{(M+1) \times n}."
        "\n$$"
    )
    out = render(src)
    # Body of the formula appears verbatim (LaTeX commands and underscores intact).
    assert r"G_{\Omega_M, Y}" in out
    assert r"\bigl(f(m y_j)\bigr)_{m = 0, \ldots, M}^{\,j = 1, \ldots, n}" in out
    assert r"\bigl(e^{a m y_j}\bigr)_{m, j}" in out
    assert r"\mathbb{C}^{(M+1) \times n}" in out
    # And no spurious <em> from markdown chewing on _..._ pairs.
    assert "<em>" not in out


def test_emphasis_outside_math_still_works():
    out = render(r"Hello $\alpha$, this is _italic_ next to $x_1$.")
    assert "<em>italic</em>" in out
    assert r"$\alpha$" in out
    assert "$x_1$" in out


def test_smarty_does_not_mangle_double_dash_inside_math():
    # smarty extension turns "--" into en-dash outside math. Make sure math
    # is untouched.
    out = render(r"Range $a -- b$ vs prose -- here.")
    assert "$a -- b$" in out  # math intact
    # outside-math en-dash transformation
    assert "&ndash;" in out or "–" in out


def test_display_math_spans_multiple_lines():
    src = "$$\na + b\nc + d\n$$"
    out = render(src)
    assert "a + b" in out
    assert "c + d" in out
    # placeholder should NOT leak
    assert "MATH" not in out or "\x00" not in out


def test_no_math_input_unchanged_behavior():
    out = render("# Title\n\nBody _italic_.")
    assert "<h1>Title</h1>" in out
    assert "<em>italic</em>" in out


def test_empty_input():
    assert render("") == ""
    assert render(None) == ""

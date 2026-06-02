"""LaTeX JSON-escape normalization tests (Python + TS parity cases)."""

from __future__ import annotations

from agentpod_agent.latex_normalize import normalize_latex_input


def test_backspace_fix_begin_outside_math():
    corrupted = "\x08egin{pmatrix} a & b \\end{pmatrix}"
    assert normalize_latex_input(corrupted) == "\\begin{pmatrix} a & b \\end{pmatrix}"


def test_backspace_fix_inside_block_math():
    corrupted = "$$\x08egin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}$$"
    assert (
        normalize_latex_input(corrupted)
        == "$$\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}$$"
    )


def test_frac_inside_block_math():
    corrupted = "$$\x0crac{a}{b}$$"
    assert normalize_latex_input(corrupted) == "$$\\frac{a}{b}$$"


def test_text_inside_inline_math():
    corrupted = "$\x09ext{hello}$"
    assert normalize_latex_input(corrupted) == "$\\text{hello}$"


def test_right_inside_block_math():
    corrupted = "$$\\left(\x0dight)$$"
    assert normalize_latex_input(corrupted) == "$$\\left(\\right)$$"


def test_newline_command_inside_math():
    corrupted = "$$a\newline b$$"
    assert normalize_latex_input(corrupted) == "$$a\\newline b$$"


def test_crlf_inside_block_math_unchanged():
    content = "$$\\begin{pmatrix}\r\na & b\r\n\\end{pmatrix}$$"
    assert normalize_latex_input(content) == content


def test_tab_indent_in_code_fence_unchanged():
    content = "```python\n\tdef foo():\n\t    pass\n```"
    assert normalize_latex_input(content) == content


def test_plain_text_unchanged():
    assert normalize_latex_input("price is 100 dollars") == "price is 100 dollars"

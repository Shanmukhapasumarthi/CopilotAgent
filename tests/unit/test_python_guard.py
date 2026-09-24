"""Guards on generated Python."""

from app.tools.python_guard import validate_python


def test_valid_solution_is_accepted() -> None:
    source = "def add(a, b):\n    return a + b\n"
    assert validate_python(source, kind="solution").ok


def test_syntax_error_is_rejected() -> None:
    result = validate_python("def add(a, b)\n    return a + b\n", kind="solution")
    assert result.ok is False
    assert "SyntaxError" in (result.error or "")


def test_disallowed_import_is_rejected() -> None:
    result = validate_python("import subprocess\n", kind="solution")
    assert result.ok is False
    assert "subprocess" in (result.error or "")


def test_open_is_rejected() -> None:
    result = validate_python("def leak():\n    return open('/etc/passwd').read()\n", kind="solution")
    assert result.ok is False
    assert "open" in (result.error or "")


def test_oversized_source_is_rejected() -> None:
    source = "x = 1\n" + ("a" * 50)
    result = validate_python(source, kind="solution", max_chars=10)
    assert result.ok is False
    assert "exceeds" in (result.error or "")


def test_pytest_import_allowed_in_tests() -> None:
    source = "import pytest\nfrom solution import add\n\ndef test_add():\n    assert add(1, 1) == 2\n"
    assert validate_python(source, kind="tests").ok

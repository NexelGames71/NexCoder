"""Tests for the sample_app math utility module."""


def test_add():
    from sample_app.src.math_utils import add
    assert add(1, 2) == 3


def test_multiply():
    from sample_app.src.math_utils import multiply
    assert multiply(2, 3) == 6

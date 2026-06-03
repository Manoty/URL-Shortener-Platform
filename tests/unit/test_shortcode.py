# tests/unit/test_shortcode.py
"""
Unit tests for short code generation.
These tests have zero dependencies — no database, no HTTP, no fixtures.
They run fast and test pure logic.
"""

import pytest
from app.utils.shortcode import generate_short_code, is_valid_short_code, ALPHABET


class TestGenerateShortCode:

    def test_default_length_is_seven(self):
        code = generate_short_code()
        assert len(code) == 7

    def test_custom_length(self):
        for length in [3, 5, 10, 15]:
            code = generate_short_code(length=length)
            assert len(code) == length

    def test_only_base62_characters(self):
        allowed = set(ALPHABET)
        for _ in range(100):
            code = generate_short_code()
            assert all(c in allowed for c in code), f"Invalid char in: {code}"

    def test_generates_unique_codes(self):
        """Statistically, 1000 codes should all be unique."""
        codes = {generate_short_code() for _ in range(1000)}
        assert len(codes) == 1000

    def test_codes_are_strings(self):
        assert isinstance(generate_short_code(), str)


class TestIsValidShortCode:

    def test_valid_alphanumeric(self):
        assert is_valid_short_code("abc123") is True

    def test_valid_with_hyphen(self):
        assert is_valid_short_code("my-link") is True

    def test_valid_with_underscore(self):
        assert is_valid_short_code("my_link") is True

    def test_invalid_with_space(self):
        assert is_valid_short_code("my link") is False

    def test_invalid_with_slash(self):
        assert is_valid_short_code("my/link") is False

    def test_invalid_empty_string(self):
        assert is_valid_short_code("") is False

    def test_invalid_none(self):
        assert is_valid_short_code(None) is False

    def test_invalid_special_chars(self):
        assert is_valid_short_code("link@me!") is False
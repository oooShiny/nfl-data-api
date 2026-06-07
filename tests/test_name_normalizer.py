"""Unit tests for deterministic player-name normalization (pure string transforms)."""

import pytest

from pipeline.silver.name_normalizer import (
    extract_suffix,
    first_initial,
    last_name_key,
    normalize_display,
    normalize_for_comparison,
    remove_diacritics,
)


class TestExtractSuffix:
    @pytest.mark.parametrize(
        "name, expected",
        [
            ("Patrick Mahomes II", ("Patrick Mahomes", "II")),
            ("Robert Griffin III", ("Robert Griffin", "III")),
            ("Ken Griffey Jr.", ("Ken Griffey", "Jr")),
            ("Ken Griffey Jr", ("Ken Griffey", "Jr")),
            ("Odell Beckham Sr.", ("Odell Beckham", "Sr")),
            ("Steve McNair", ("Steve McNair", "")),
            ("", ("", "")),
        ],
    )
    def test_extract_suffix(self, name, expected):
        assert extract_suffix(name) == expected

    def test_comma_separated_suffix(self):
        assert extract_suffix("Patrick Mahomes, II") == ("Patrick Mahomes", "II")


class TestRemoveDiacritics:
    @pytest.mark.parametrize(
        "name, expected",
        [
            ("Amon-Ra St. Brown", "Amon-Ra St. Brown"),  # ASCII passthrough
            ("José", "Jose"),
            ("Nuñez", "Nunez"),
            ("plain", "plain"),
        ],
    )
    def test_remove_diacritics(self, name, expected):
        assert remove_diacritics(name) == expected


class TestNormalizeForComparison:
    @pytest.mark.parametrize(
        "name, expected",
        [
            ("S.McNair", "smcnair"),
            ("Steve McNair", "steve mcnair"),
            ("Amon-Ra St. Brown", "amonra st brown"),
            ("Patrick Mahomes II", "patrick mahomes"),  # suffix dropped
            ("O'Dell  Beckham", "odell beckham"),  # apostrophe + double space
            ("", ""),
        ],
    )
    def test_normalize_for_comparison(self, name, expected):
        assert normalize_for_comparison(name) == expected

    def test_idempotent(self):
        once = normalize_for_comparison("Amon-Ra St. Brown")
        assert normalize_for_comparison(once) == once


class TestNormalizeDisplay:
    @pytest.mark.parametrize(
        "name, expected",
        [
            ("S.McNair", "S. McNair"),
            ("Steve   McNair", "Steve McNair"),
            ("  Patrick Mahomes  ", "Patrick Mahomes"),
            ("", ""),
        ],
    )
    def test_normalize_display(self, name, expected):
        assert normalize_display(name) == expected

    def test_does_not_expand_initials(self):
        # display cleanup must not invent a full first name
        assert normalize_display("S. McNair") == "S. McNair"


class TestBlockingKeys:
    @pytest.mark.parametrize(
        "name, expected",
        [
            ("Patrick Mahomes II", "mahomes"),
            ("Amon-Ra St. Brown", "brown"),
            ("Steve McNair", "mcnair"),
            ("", ""),
        ],
    )
    def test_last_name_key(self, name, expected):
        assert last_name_key(name) == expected

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("Patrick Mahomes", "p"),
            ("S.McNair", "s"),
            ("", ""),
        ],
    )
    def test_first_initial(self, name, expected):
        assert first_initial(name) == expected

"""Sanity checks on pipeline configuration."""

from pipeline.config import LARGE_TAGS, RELEASE_TAGS


def test_release_tags_unique():
    assert len(RELEASE_TAGS) == len(set(RELEASE_TAGS))


def test_large_tags_subset_of_release_tags():
    assert LARGE_TAGS.issubset(set(RELEASE_TAGS))


def test_release_tags_nonempty():
    assert len(RELEASE_TAGS) > 0
    assert all(isinstance(t, str) and t for t in RELEASE_TAGS)

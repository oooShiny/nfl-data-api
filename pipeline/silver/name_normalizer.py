"""Deterministic player name normalization — no DB access, pure string transforms."""

import re
import unicodedata

# Generational suffixes to strip before comparison
_SUFFIXES = re.compile(
    r'\s*,?\s*\b(Jr\.?|Sr\.?|II|III|IV|V|Esq\.?)\s*$',
    re.IGNORECASE,
)

# "F.Lastname" or "F. Lastname" patterns used in older PBP data
_INITIAL_COMPACT = re.compile(r'^([A-Z])\.\s*([A-Za-z])')
_INITIAL_SPACED  = re.compile(r'^([A-Z])\. ([A-Za-z])')


def extract_suffix(name: str) -> tuple[str, str]:
    """Split 'Patrick Mahomes II' → ('Patrick Mahomes', 'II')."""
    if not name:
        return name, ''
    m = _SUFFIXES.search(name)
    if m:
        return name[:m.start()].strip(), m.group(1).rstrip('.')
    return name.strip(), ''


def remove_diacritics(name: str) -> str:
    """'Amon-Ra St. Brown' → 'Amon-Ra St. Brown' (passthrough for ASCII names,
    strips combining characters from accented letters)."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', name)
        if unicodedata.category(c) != 'Mn'
    )


def normalize_for_comparison(name: str) -> str:
    """Return a lowercase, punctuation-stripped key suitable for fuzzy matching.

    'S.McNair'  → 'smcnair'
    'Steve McNair' → 'steve mcnair'
    'Amon-Ra St. Brown' → 'amonra st brown'
    """
    if not name:
        return ''
    base, _ = extract_suffix(name)
    base = remove_diacritics(base)
    base = base.lower()
    base = re.sub(r'[.\-\']', '', base)   # strip . - '
    base = re.sub(r'\s+', ' ', base).strip()
    return base


def normalize_display(name: str) -> str:
    """Light cleanup for display: fix 'S.McNair' → 'S. McNair', collapse spaces.
    Does NOT expand initials to full names — that requires the dim_players lookup.
    """
    if not name:
        return name
    name = name.strip()
    name = re.sub(r'\s+', ' ', name)
    # Add space after initial-dot if missing: "S.McNair" → "S. McNair"
    name = _INITIAL_COMPACT.sub(lambda m: f'{m.group(1)}. {m.group(2)}', name)
    return name


def last_name_key(name: str) -> str:
    """Extract last name token for blocking: 'Patrick Mahomes II' → 'mahomes'."""
    base, _ = extract_suffix(name)
    parts = normalize_for_comparison(base).split()
    return parts[-1] if parts else ''


def first_initial(name: str) -> str:
    """Extract first initial for blocking: 'Patrick Mahomes' → 'p'."""
    key = normalize_for_comparison(name)
    return key[0] if key else ''

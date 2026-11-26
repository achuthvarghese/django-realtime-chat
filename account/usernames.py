"""Username rules.

A username is 3 to 30 characters of lowercase letters, digits and single
underscores. It starts with a letter and does not end with an underscore.
Underscores stand in for spaces. See docs/screens.md#username-rules.
"""

import re

from django.core.exceptions import ValidationError

MIN_LENGTH = 3
MAX_LENGTH = 30
PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
HELP_TEXT = (
    f"{MIN_LENGTH}–{MAX_LENGTH} characters: lowercase letters, numbers and _ "
    "(for spaces). Start with a letter; no _ at the end or twice in a row."
)


def is_valid(value):
    return MIN_LENGTH <= len(value) <= MAX_LENGTH and bool(PATTERN.match(value))


def tidy(value):
    """What the signup field does while you type: lowercase, and turn runs
    of spaces or underscores into one underscore. Other characters stay so
    validation can point them out."""
    value = (value or "").strip().lower()
    value = re.sub(r"\s+", "_", value)
    return re.sub(r"_{2,}", "_", value)


def validate_username(value):
    """Raise ValidationError with the first broken rule, in plain words."""
    if len(value) < MIN_LENGTH:
        raise ValidationError(
            f"Use at least {MIN_LENGTH} characters.", code="too_short"
        )
    if len(value) > MAX_LENGTH:
        raise ValidationError(f"Use at most {MAX_LENGTH} characters.", code="too_long")
    if re.search(r"[^a-z0-9_]", value):
        raise ValidationError(
            "Use only lowercase letters, numbers and _.", code="characters"
        )
    if not value[0].isalpha():
        raise ValidationError("Start with a letter.", code="start")
    if value.endswith("_"):
        raise ValidationError("Don't end with _.", code="end")
    if "__" in value:
        raise ValidationError("Don't put two _ in a row.", code="double")
    if not PATTERN.match(value):  # safety net; the checks above cover it
        raise ValidationError(HELP_TEXT, code="invalid")


def conform(value):
    """Best valid form of an existing username, used by the migration that
    renames accounts created before these rules. Uniqueness is handled by
    the caller."""
    value = (value or "").lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    value = re.sub(r"_{2,}", "_", value)
    if not value or not value[0].isalpha():
        value = f"user_{value}".rstrip("_")
    if len(value) < MIN_LENGTH:
        value = f"{value}_user"
    return value[:MAX_LENGTH].rstrip("_")


def unique_variant(base, taken):
    """`base`, or `base_2`, `base_3`… trimmed to fit, not already in `taken`."""
    if base not in taken:
        return base
    n = 2
    while True:
        suffix = f"_{n}"
        candidate = base[: MAX_LENGTH - len(suffix)].rstrip("_") + suffix
        if candidate not in taken:
            return candidate
        n += 1

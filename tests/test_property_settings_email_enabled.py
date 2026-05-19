"""
Property 1: EMAIL_ENABLED is False for any non-"true" env var value.
Feature: email-delivery-fix, Property 1: EMAIL_ENABLED parsing

**Validates: Requirements 1.2**
"""

import importlib
import os

from hypothesis import given, settings
from hypothesis import strategies as st


def _load_email_enabled(env_value: str) -> bool:
    """Reload src.config.settings with EMAIL_ENABLED set to *env_value* and
    return the resulting constant.

    Using importlib.reload ensures the module-level expression
    ``os.getenv("EMAIL_ENABLED", "false").lower() == "true"``
    is re-evaluated with the patched environment.
    """
    import src.config.settings as settings_module

    os.environ["EMAIL_ENABLED"] = env_value
    try:
        importlib.reload(settings_module)
        return settings_module.EMAIL_ENABLED
    finally:
        # Restore env so other tests are not affected
        del os.environ["EMAIL_ENABLED"]


# ---------------------------------------------------------------------------
# Property 1: EMAIL_ENABLED is False for any non-"true" env var value
# ---------------------------------------------------------------------------


@given(
    value=st.text(
        alphabet=st.characters(
            blacklist_categories=("Cs",), blacklist_characters="\x00"
        )
    ).filter(lambda s: s.lower() != "true")
)
@settings(max_examples=200)
def test_email_enabled_false_for_non_true_values(value: str) -> None:
    """**Validates: Requirements 1.2**

    For any string that is not equal to "true" (case-insensitive),
    EMAIL_ENABLED SHALL evaluate to False.
    """
    result = _load_email_enabled(value)
    assert (
        result is False
    ), f"Expected EMAIL_ENABLED=False for env value {value!r}, got {result!r}"


# ---------------------------------------------------------------------------
# Complementary: EMAIL_ENABLED is True for all case variants of "true"
# (validates Requirement 1.3 as a sanity check)
# ---------------------------------------------------------------------------


@given(
    value=st.sampled_from(
        ["true", "True", "TRUE", "tRuE", "TrUe", "trUE", "truE", "tRUE"]
    )
)
@settings(max_examples=50)
def test_email_enabled_true_for_case_insensitive_true(value: str) -> None:
    """**Validates: Requirements 1.3**

    For any case-insensitive variant of "true", EMAIL_ENABLED SHALL be True.
    """
    result = _load_email_enabled(value)
    assert (
        result is True
    ), f"Expected EMAIL_ENABLED=True for env value {value!r}, got {result!r}"

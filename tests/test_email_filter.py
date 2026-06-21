"""Email junk-filtering + prioritization tests (11 tests)."""
from __future__ import annotations

from .conftest import wfg


def test_junk_substring_filtering():
    assert wfg.is_junk_email("hello@example.com")
    assert wfg.is_junk_email("noise@cloudflare.net")
    assert wfg.is_junk_email("x@domain.com")
    assert wfg.is_junk_email("support@northstar-demo.fictional-test")


def test_no_reply_variants_filtered():
    assert wfg.is_junk_email("noreply@northstar-demo.fictional-test")
    assert wfg.is_junk_email("no-reply@northstar-demo.fictional-test")


def test_image_extension_filtering():
    assert wfg.is_junk_email("logo@2x.png")
    assert wfg.is_junk_email("sprite@demo.svg")
    assert wfg.is_junk_email("style@demo.css")


def test_empty_and_none_are_junk():
    assert wfg.is_junk_email("")
    assert wfg.is_junk_email(None)


def test_real_emails_pass():
    assert not wfg.is_junk_email("chef@northstar-demo.fictional-test")
    assert not wfg.is_junk_email("owner@halcyon-demo.fictional-test")


def test_personal_beats_info():
    emails = [
        "info@northstar-demo.fictional-test",
        "chef@northstar-demo.fictional-test",
    ]
    assert wfg.pick_best_email(emails) == "chef@northstar-demo.fictional-test"


def test_personal_beats_reservation_and_info():
    emails = [
        "reservation@polestar-demo.fictional-test",
        "info@polestar-demo.fictional-test",
        "owner@polestar-demo.fictional-test",
    ]
    assert wfg.pick_best_email(emails) == "owner@polestar-demo.fictional-test"


def test_info_used_when_only_generic():
    emails = [
        "reservation@cedar-demo.fictional-test",
        "info@cedar-demo.fictional-test",
    ]
    # No personal address; info@ is preferred over reservation@.
    assert wfg.pick_best_email(emails) == "info@cedar-demo.fictional-test"


def test_fallback_to_first_when_only_role():
    emails = [
        "reservation@riverbend-demo.fictional-test",
        "booking@riverbend-demo.fictional-test",
    ]
    # No personal, no info@/contact@; fall back to first in list.
    assert wfg.pick_best_email(emails) == "reservation@riverbend-demo.fictional-test"


def test_empty_list_returns_empty_string():
    assert wfg.pick_best_email([]) == ""


def test_case_insensitive_prioritization():
    emails = [
        "INFO@halcyon-demo.fictional-test",
        "Chef@halcyon-demo.fictional-test",
    ]
    # Mixed case still resolves to the personal address.
    assert wfg.pick_best_email(emails) == "Chef@halcyon-demo.fictional-test"

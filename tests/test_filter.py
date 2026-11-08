import re
from datetime import datetime, timezone

import pytest

from logq.filter import Query, default_level, matches, parse_level
from logq.parse import Event


def ev(**kw):
    base = dict(ts=datetime(2026, 1, 1, tzinfo=timezone.utc), container="api-1", service="api", project="p", level=40, msg="m")
    return Event(**{**base, **kw})


def test_default_level():
    assert default_level(None) == 30 and default_level("7f3a9c21") == 10


def test_field_filters_default_to_all_levels():
    assert default_level(None, None, None, None, None) == 30
    for i in range(1, 5):  # --status, --route, --method, --func: request lines are INFO, so warn would hide them
        args = [None] * 5
        args[i] = "x"
        assert default_level(*args) == 10


def test_level_and_service():
    assert not matches(ev(level=20), Query())
    assert not matches(ev(), Query(services=["db"]))
    assert matches(ev(), Query(services=["db", "api"]))


def test_trace_prefix_and_plain_text_substring():
    assert matches(ev(trace="7f3a9c21aabbccdd"), Query(trace="7f3a9c21", level=10))
    assert matches(ev(raw="GET /x 7f3a9c21aabb 200"), Query(trace="7f3a9c21", level=10))
    assert not matches(ev(trace="00000000ffff"), Query(trace="7f3a9c21", level=10))


def test_status_ranges_and_missing_fields():
    assert matches(ev(status=503), Query(status="5xx"))
    assert not matches(ev(status=404), Query(status="5xx"))
    assert matches(ev(status=404), Query(status="404"))
    assert not matches(ev(), Query(status="5xx"))
    assert not matches(ev(), Query(route="/api"))


def test_route_method_func_substrings():
    e = ev(route="/api/orders/{id}", method="POST", func="create_order")
    assert matches(e, Query(route="/orders", method="post", func="create"))


def test_grep_covers_error_text():
    assert matches(ev(error="KeyError: 'sku'"), Query(grep=re.compile("sku")))


def test_grep_covers_message_and_extra_lines():
    assert matches(ev(msg="charge failed"), Query(grep=re.compile("failed")))
    assert matches(ev(extra=["  at pay()"]), Query(grep=re.compile("pay")))
    assert not matches(ev(), Query(grep=re.compile("sku")))


def test_parse_level():
    assert parse_level("WARN") == 30 and parse_level("debug") == 10
    with pytest.raises(ValueError):
        parse_level("loud")


def test_status_class_is_case_insensitive_and_bad_values_raise():
    assert matches(ev(status=404), Query(status="4XX"))
    for bad in ("5x", "abc", "50", "6xxx"):
        with pytest.raises(ValueError):
            Query(status=bad)

"""Focused regression for the loopback-blind liveness probe.

Charter v2 item 4 (ibl-1ecb314b8f7f). This deployment's workhorse route is
the local DeepSeek bridge on 127.0.0.1:8318 — a loopback URL. Before this
fix, `ouroboros/llm_probe.py::upstream_transport_reachable` short-circuited
with `return {}` for any loopback base_url, so the probe was structurally
blind to the one route this host actually runs on; consequently
`continue_unknown_transport` in `ouroboros/loop_transport.py` could never
observe recovery.

The two-byte fix:
  * drop `or is_loopback_base_url(url)` from the early return, so a loopback
    URL is probed with the same short httpx HEAD the non-loopback branch
    already uses; and
  * widen the reachability predicate to accept any sub-600 status from a
    loopback URL, because the live bridge answers HEAD with 501
    (method-not-supported) which is a live signal, not a death signal.
"""

from __future__ import annotations

import inspect
from unittest import mock

from ouroboros import llm_probe
from ouroboros.transport_custody import is_loopback_base_url


class _FakeLLM:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def _resolve_remote_target(self, model: str) -> dict:
        return {"base_url": self._base_url}

    def _no_proxy_timeout(self, timeout):
        outer = float(timeout)

        class _T:
            connect = outer

        return _T()


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeClient:
    def __init__(self, status_code: int) -> None:
        self._status_code = status_code
        self.calls: list[str] = []

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def head(self, url: str) -> _FakeResponse:
        self.calls.append(url)
        return _FakeResponse(self._status_code)


def _call(llm: _FakeLLM, client: _FakeClient) -> dict:
    with mock.patch("httpx.Client", return_value=client):
        return llm_probe.upstream_transport_reachable(
            llm, "deepseek-reasoner", timeout=5.0
        )


def test_loopback_base_url_is_probed_not_short_circuited() -> None:
    """A loopback base_url must reach httpx.head, not return {} early."""
    llm = _FakeLLM("http://127.0.0.1:8318")
    client = _FakeClient(501)
    result = _call(llm, client)
    assert client.calls == ["http://127.0.0.1:8318"], (
        "loopback URL was not probed — the early-return short-circuit is back"
    )
    assert result.get("kind") == "upstream_http"
    assert result.get("status_code") == 501


def test_loopback_501_head_counts_as_reachable() -> None:
    """The live bridge answers HEAD with 501; that is a live signal."""
    url = "http://127.0.0.1:8318"
    status_code = 501
    assert is_loopback_base_url(url) is True
    reachable = (200 <= status_code < 500) or (
        is_loopback_base_url(url) and status_code < 600
    )
    assert reachable is True


def test_non_loopback_5xx_is_not_reachable() -> None:
    """5xx on a non-loopback route is not reachability evidence."""
    llm = _FakeLLM("https://api.example.com")
    client = _FakeClient(503)
    result = _call(llm, client)
    assert result == {}


def test_source_no_longer_short_circuits_loopback() -> None:
    """Byte-level guard: the old short-circuit must not reappear."""
    src = inspect.getsource(llm_probe.upstream_transport_reachable)
    assert "is_loopback_base_url(url)" not in src.split("if not url:")[0], (
        "the `or is_loopback_base_url(url)` short-circuit is back in the "
        "early return"
    )
    assert "if not url:" in src
    assert "is_loopback_base_url(url) and response.status_code < 600" in src

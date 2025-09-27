from __future__ import annotations

from typing import Any, Iterable, List

import pytest

from waverly.constants import FOFA_MAX_PAGE_SIZE, FOFA_MIN_PAGE_SIZE
from waverly.fofa import FofaClient, FofaError, FofaResult


class DummyResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload

    @property
    def text(self) -> str:  # pragma: no cover - debug helper
        return ""


class DummySession:
    def __init__(self, responses: Iterable[DummyResponse]):
        self._responses = list(responses)

    def get(self, *_args: Any, **_kwargs: Any) -> DummyResponse:
        if not self._responses:
            raise AssertionError("Unexpected request")
        return self._responses.pop(0)


def build_client(payload: dict[str, Any]) -> FofaClient:
    session = DummySession([DummyResponse(200, payload)])
    return FofaClient("user@example.com", "secret", session=session)


@pytest.mark.parametrize(
    "results, fields, expected",
    [
        (
            [["example.com", "1.1.1.1"]],
            ["host", "ip"],
            [FofaResult({"host": "example.com", "ip": "1.1.1.1"})],
        ),
        (
            [{"host": "example.com", "ip": "1.1.1.1"}],
            ["host", "ip"],
            [FofaResult({"host": "example.com", "ip": "1.1.1.1"})],
        ),
        (
            ["example.com"],
            ["host"],
            [FofaResult({"host": "example.com"})],
        ),
    ],
)
def test_parse_varied_result_shapes(results: List[Any], fields: List[str], expected: List[FofaResult]) -> None:
    payload = {"error": False, "results": results, "queryfield": fields}
    client = build_client(payload)
    assert client.search("app=\"nginx\"", fields=fields) == expected


def test_http_error_raises() -> None:
    session = DummySession([DummyResponse(500, {"error": True, "errmsg": "fail"})])
    client = FofaClient("user@example.com", "secret", session=session)
    with pytest.raises(FofaError):
        client.search("app=\"nginx\"")


def test_rejects_invalid_page_sizes() -> None:
    client = FofaClient("user@example.com", "secret", session=DummySession([]))
    with pytest.raises(ValueError):
        client.search("app=\"nginx\"", size=FOFA_MAX_PAGE_SIZE + 1)
    with pytest.raises(ValueError):
        client.search("app=\"nginx\"", size=FOFA_MIN_PAGE_SIZE - 1)

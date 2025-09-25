from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

try:  # pragma: no cover - optional dependency fallback
    import requests  # type: ignore
    RequestError = requests.RequestException  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - executed in minimal envs
    class RequestError(Exception):
        pass

    class _DummySession:  # minimal stub to provide helpful error messages
        def get(self, *_args, **_kwargs):
            raise RuntimeError(
                "The 'requests' package is required to use FOFA API features. "
                "Install it with 'pip install requests'."
            )

    class _DummyRequestsModule:
        Session = _DummySession

    requests = _DummyRequestsModule()  # type: ignore


class FofaError(RuntimeError):
    """Raised when the FOFA API returns an error."""


@dataclass
class FofaResult:
    """Normalized FOFA query result."""

    data: Dict[str, Optional[str]]

    def __getitem__(self, item: str) -> Optional[str]:
        return self.data.get(item)

    def get(self, item: str, default: Optional[str] = None) -> Optional[str]:
        return self.data.get(item, default)


class FofaClient:
    """Light-weight FOFA API client wrapper."""

    def __init__(
        self,
        email: str,
        key: str,
        *,
        base_url: str = "https://fofa.info/api/v1",
        session: Optional[requests.Session] = None,
        verify_ssl: bool = True,
        timeout: float = 30.0,
    ) -> None:
        if not email or not key:
            raise ValueError("FOFA email and key must be provided.")
        self.email = email
        self.key = key
        self.base_url = base_url.rstrip("/")
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._session = session or requests.Session()

    @property
    def session(self) -> requests.Session:
        return self._session

    def build_query(self, expression: str) -> str:
        if not expression:
            raise ValueError("Search expression cannot be empty.")
        return base64.b64encode(expression.encode("utf-8")).decode("utf-8")

    def search(
        self,
        expression: str,
        *,
        page: int = 1,
        size: int = 100,
        fields: Optional[Iterable[str]] = None,
    ) -> List[FofaResult]:
        """Execute a search and return normalized results."""

        url = f"{self.base_url}/search/all"
        payload = {
            "email": self.email,
            "key": self.key,
            "qbase64": self.build_query(expression),
            "page": page,
            "size": size,
        }
        if fields:
            payload["fields"] = ",".join(fields)
        response = self.session.get(url, params=payload, timeout=self.timeout, verify=self.verify_ssl)
        if response.status_code >= 400:
            raise FofaError(f"FOFA API error: {response.status_code} {response.text}")
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise FofaError("Invalid JSON returned from FOFA API") from exc
        if not payload.get("error", False):
            return self._parse_results(payload, fields)
        raise FofaError(payload.get("errmsg", "Unknown FOFA error"))

    def validate_credentials(self) -> bool:
        """Perform a lightweight request to validate credentials."""

        try:
            self.search("app=""nginx""", page=1, size=1)
        except (FofaError, ValueError, RequestError):
            return False
        return True

    def _parse_results(
        self, payload: Dict[str, any], fields: Optional[Iterable[str]]
    ) -> List[FofaResult]:
        field_list = list(fields) if fields else payload.get("queryfield", [])
        results = []
        for raw in payload.get("results", []):
            data = {field_list[idx] if idx < len(field_list) else str(idx): value for idx, value in enumerate(raw)}
            results.append(FofaResult(data))
        return results


def extract_hosts(results: Iterable[FofaResult]) -> List[str]:
    hosts: List[str] = []
    for result in results:
        host = result.get("host") or result.get("ip")
        if host:
            hosts.append(str(host))
    return hosts


__all__ = ["FofaClient", "FofaError", "FofaResult", "extract_hosts", "RequestError"]


import time
from urllib.parse import quote

import requests
from django.conf import settings

from apps.carriers.exceptions import PacoteVicioClientError, PacoteVicioServerError

DEFAULT_USER_AGENT = "postman/1.0"


def _digits(value) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _error_code(resp: "requests.Response") -> str:
    try:
        body = resp.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return ""
    code = error.get("code")
    return code if isinstance(code, str) else ""


def _error_message(resp: "requests.Response") -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:300]
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return f"{error.get('message')} (request_id={error.get('request_id', '?')})"
    return resp.text[:300]


class PacoteVicioClient:
    def __init__(self, auth_base: str | None = None, timeout: int | None = None):
        self.base_url = auth_base or settings.PACOTE_VICIO_BASE_URL
        self.api_key = getattr(settings, "PACOTE_VICIO_API_KEY", "")
        self.timeout = timeout or settings.PACOTE_VICIO_TIMEOUT
        self.retry_level = getattr(settings, "PACOTE_VICIO_RETRY_LEVEL", "high")
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-Key": self.api_key,
            "User-Agent": getattr(settings, "PACOTE_VICIO_USER_AGENT", "") or DEFAULT_USER_AGENT,
        })

    def _track_url(self, courier: str, tracking_code: str, retry_level: str) -> str:
        base = self.base_url.rstrip("/")
        path = f"v1/track/{quote(courier, safe='')}/{quote(tracking_code, safe='')}"
        return f"{base}/{path}?retry_level={retry_level}"

    def _get(self, url: str, headers: dict) -> "requests.Response":
        return self.session.get(url, headers=headers, timeout=self.timeout)

    def fetch(self, courier: str, tracking_code: str, document: str = "", retry_level: str | None = None) -> dict:
        retry_level = retry_level or self.retry_level
        url = self._track_url(courier, tracking_code, retry_level)
        headers = {}
        if document:
            headers["X-Tracking-Document"] = _digits(document)
        try:
            resp = self._get(url, headers)
        except requests.RequestException as exc:
            raise PacoteVicioServerError(f"Falha de rede/timeout: {exc}") from exc
        for _ in range(1):
            if resp.status_code == 429:
                wait = _retry_after(resp)
                time.sleep(wait)
                try:
                    resp = self._get(url, headers)
                except requests.RequestException:
                    pass
            elif resp.status_code in range(500, 600):
                time.sleep(1)
                try:
                    resp = self._get(url, headers)
                except requests.RequestException:
                    pass
            else:
                break
        if not resp.ok:
            if resp.status_code == 429:
                raise PacoteVicioServerError(f"Limite da API atingido (HTTP 429 {_error_code(resp)}).")
            if 500 <= resp.status_code < 600:
                raise PacoteVicioServerError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            raise PacoteVicioClientError(
                resp.status_code,
                f"{resp.status_code} {_error_code(resp)}: {_error_message(resp)}",
                code=_error_code(resp),
            )
        return resp.json()


def _retry_after(resp: "requests.Response") -> int:
    try:
        wait = int(resp.headers.get("Retry-After") or 1)
    except (TypeError, ValueError):
        return 1
    return max(1, min(wait, 10))
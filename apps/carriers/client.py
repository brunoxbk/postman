import time

import requests
from django.conf import settings

from apps.carriers.exceptions import PacoteVicioClientError, PacoteVicioServerError


class PacoteVicioClient:
    def __init__(self, auth_base: str | None = None, timeout: int | None = None):
        self.base_url = auth_base or settings.PACOTE_VICIO_BASE_URL
        self.api_key = getattr(settings, "PACOTE_VICIO_API_KEY", "")
        self.timeout = timeout or settings.PACOTE_VICIO_TIMEOUT

    def _get(self, url: str, params: dict) -> "requests.Response":
        return requests.get(
            url,
            params=params,
            timeout=self.timeout,
            headers={"X-RapidAPI-Key": self.api_key},
        )

    def fetch(self, path: str, params: dict) -> dict:
        url = f"{self.base_url.rstrip('/')}/{path.strip('/')}"
        try:
            resp = self._get(url, params)
        except requests.RequestException as exc:
            raise PacoteVicioServerError(f"Falha de rede/timeout: {exc}") from exc
        if resp.status_code in (429, *range(500, 600)):
            time.sleep(1)
            try:
                resp = self._get(url, params)
            except requests.RequestException:
                pass
        if not resp.ok:
            if resp.status_code == 429:
                raise PacoteVicioServerError("Rate limit da API atingido (HTTP 429).")
            if 400 <= resp.status_code < 500:
                raise PacoteVicioClientError(resp.status_code, resp.text[:300])
            raise PacoteVicioServerError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()
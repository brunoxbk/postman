import re

from apps.carriers.constants import (
    CARRIER_ALIEXPRESS,
    CARRIER_ANJUN,
    CARRIER_CORREIOS,
    CARRIER_JTEXPRESS,
    CARRIER_SHOPEE,
    CARRIER_TOTALEXPRESS,
)
from apps.carriers.parsing import parse_date, parse_datetime
from apps.carriers.payload import EventData, NormalizedPayload


def _clean(text) -> str:
    if text is None:
        return ""
    return " ".join(str(text).split())


class BaseAdapter:
    nid: str = ""
    name: str = ""
    requires_document: bool = False


class CorreiosAdapter(BaseAdapter):
    nid = CARRIER_CORREIOS
    name = "Correios"


class AliExpressAdapter(BaseAdapter):
    nid = CARRIER_ALIEXPRESS
    name = "AliExpress"


class ShopeeAdapter(BaseAdapter):
    nid = CARRIER_SHOPEE
    name = "Shopee Xpress"


class AnjunAdapter(BaseAdapter):
    nid = CARRIER_ANJUN
    name = "Anjun Express"


class JTExpressAdapter(BaseAdapter):
    nid = CARRIER_JTEXPRESS
    name = "J&T Express"
    requires_document = True


class TotalExpressAdapter(BaseAdapter):
    nid = CARRIER_TOTALEXPRESS
    name = "Total Express"


ADAPTERS = {
    a.nid: a()
    for a in (CorreiosAdapter, AliExpressAdapter, ShopeeAdapter, AnjunAdapter, JTExpressAdapter, TotalExpressAdapter)
}


def get_adapter(nid: str):
    return ADAPTERS[nid]


_PATTERNS = {
    CARRIER_CORREIOS: re.compile(r"^[A-Z]{2}\d{9}BR$"),
    CARRIER_ALIEXPRESS: re.compile(r"^(LP\d{9,}CN|[A-Z]{2}\d{9,}CN)$", re.I),
    CARRIER_SHOPEE: re.compile(r"^BR\d{12,}$"),
    CARRIER_ANJUN: re.compile(r"^AJ\d{6,}$", re.I),
    CARRIER_JTEXPRESS: re.compile(r"^\d{10,18}$"),
    CARRIER_TOTALEXPRESS: re.compile(r"^[A-Z]{3,5}\d{6,}(?:[tx]{1,2})?$", re.I),
}


def detect_carrier(code: str) -> str | None:
    code = code.strip()
    for nid, pat in _PATTERNS.items():
        if pat.match(code):
            return nid
    return None


def is_plausible_code(value: str) -> bool:
    """Heurística mínima para distinguir um código de rastreio de texto digitado por engano
    (ex.: rótulo no campo de código). Exige dígitos, sem espaços e comprimento razoável."""
    value = (value or "").strip()
    return len(value) >= 6 and value.isalnum() and any(ch.isdigit() for ch in value)


def resolve_carrier(code: str, preferred: str = "") -> str | None:
    """Decide o carrier: usa o 'preferred' se informado, senão detecta pelo código."""
    if preferred:
        return preferred
    return detect_carrier(code)


# Status normalizados da API v1 → estado terminal do app. Somente os terminais
# (entregue/devolvida) encerram o rastreio; 'exception' mantém o ciclo ativo.
TERMINAL_V1_TO_STATE = {
    "delivered": "delivered",
    "returned": "returned",
}


def _location_string(location) -> str:
    if not isinstance(location, dict):
        return ""
    city = _clean(location.get("city"))
    state = _clean(location.get("state"))
    return " / ".join(x for x in (city, state) if x)


def normalize_v1(raw: dict) -> NormalizedPayload:
    """Converte a resposta normalizada do GET /v1/track (ver pacote_vicio.txt) em
    NormalizedPayload. Os eventos vêm do mais antigo para o mais recente; o evento
    sintético do plano Básico (status 'unknown') é preservado, como exige a API."""
    events = []
    for ev in raw.get("events") or []:
        location = _location_string(ev.get("location"))
        status = _clean(ev.get("status"))
        events.append(EventData(
            occurred_at=parse_datetime(ev.get("timestamp")),
            status_key=status or _clean(ev.get("courier_status_code")),
            status_label=_clean(ev.get("courier_status_label") or ev.get("description") or status),
            location=location,
            raw=ev,
        ))
    status = _clean(raw.get("status"))
    terminal_state = TERMINAL_V1_TO_STATE.get(status)
    is_terminal = bool(terminal_state) or bool(raw.get("delivered_at"))
    if is_terminal and not terminal_state:
        terminal_state = "delivered"
    last = events[-1] if events else None
    return NormalizedPayload(
        tracking_code=_clean(raw.get("tracking_code")),
        status_code=status,
        status_label=last.status_label if last else "",
        location=last.location if last else "",
        last_event_at=parse_datetime(raw.get("status_updated_at")) or (last.occurred_at if last else None),
        estimated_delivery=parse_date(raw.get("estimated_delivery_date")),
        is_terminal=is_terminal,
        terminal_state=terminal_state,
        events=events,
        raw=raw,
    )
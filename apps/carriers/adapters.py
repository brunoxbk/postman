import re
from datetime import date, datetime

from apps.carriers.constants import (
    CARRIER_ALIEXPRESS,
    CARRIER_ANJUN,
    CARRIER_CORREIOS,
    CARRIER_JTEXPRESS,
    CARRIER_SHOPEE,
    CARRIER_TOTALEXPRESS,
)
from apps.carriers.parsing import parse_date, parse_datetime, to_aware
from apps.carriers.payload import EventData, NormalizedPayload


def _clean(text) -> str:
    if text is None:
        return ""
    return " ".join(str(text).split())


class BaseAdapter:
    nid: str = ""
    name: str = ""
    host_path: str = ""
    requires_document: bool = False

    def build_params(self, tracking_code: str, document: str = "") -> dict:
        params = {"tracking_code": tracking_code}
        if self.requires_document:
            params["document"] = document
        return params

    def normalize(self, raw: dict) -> NormalizedPayload:
        raise NotImplementedError


class CorreiosAdapter(BaseAdapter):
    nid = CARRIER_CORREIOS
    name = "Correios"
    host_path = "/correios"

    def normalize(self, raw: dict) -> NormalizedPayload:
        events = []
        for ev in raw.get("eventos", []):
            dt = parse_datetime(ev.get("dtHrCriado", {}).get("date"))
            unidade = ev.get("unidade") or {}
            end = unidade.get("endereco") or {}
            city = _clean(end.get("cidade"))
            uf = _clean(end.get("uf"))
            location = " / ".join(x for x in (city, uf) if x)
            events.append(EventData(
                occurred_at=to_aware(dt) if dt else None,
                status_key=_clean(ev.get("codigo")),
                status_label=_clean(ev.get("descricaoWeb") or ev.get("descricao")),
                location=location,
                raw=ev,
            ))
        is_terminal = (
            any(_clean(ev.get("finalizador")).upper() == "S" for ev in raw.get("eventos", []))
            or raw.get("situacao") == "E"
        )
        events.sort(key=lambda e: e.occurred_at or datetime.min, reverse=True)
        return NormalizedPayload(
            tracking_code=raw.get("codObjeto", ""),
            status_code=_clean(raw.get("situacao")),
            status_label=events[0].status_label if events else "",
            location=events[0].location if events else "",
            last_event_at=events[0].occurred_at if events else None,
            estimated_delivery=parse_date(_clean(raw.get("dtPrevista"))),
            is_terminal=is_terminal,
            events=events,
            raw=raw,
        )


class AliExpressAdapter(BaseAdapter):
    nid = CARRIER_ALIEXPRESS
    name = "AliExpress"
    host_path = "/aliexpress"

    def normalize(self, raw: dict) -> NormalizedPayload:
        events = []
        for ev in raw.get("detailList", []):
            try:
                ts = int(ev.get("time") or 0)
            except (TypeError, ValueError):
                ts = 0
            events.append(EventData(
                occurred_at=parse_datetime(ts or None),
                status_key=_clean(ev.get("actionCode")),
                status_label=_clean(ev.get("standerdDesc") or ev.get("descTitle")),
                location=_clean(ev.get("desc")),
                raw=ev,
            ))
        status = _clean(raw.get("status"))
        status_desc = _clean(raw.get("statusDesc"))
        eta = raw.get("globalEtaInfo") or {}
        est = None
        mms = eta.get("deliveryMaxTime")
        if mms:
            est = date.fromtimestamp(int(mms) / 1000)
        events.sort(key=lambda e: e.occurred_at or datetime.min, reverse=True)
        return NormalizedPayload(
            tracking_code=raw.get("mailNo", ""),
            status_code=status,
            status_label=status_desc,
            location="",
            last_event_at=events[0].occurred_at if events else None,
            estimated_delivery=est,
            is_terminal="deliver" in (status + " " + status_desc).lower(),
            events=events,
            raw=raw,
        )


class ShopeeAdapter(BaseAdapter):
    nid = CARRIER_SHOPEE
    name = "Shopee Xpress"
    host_path = "/shopee"

    def normalize(self, raw: dict) -> NormalizedPayload:
        events = []
        for ev in raw.get("tracking_list", []):
            message = _clean(ev.get("message"))
            head = message.split("]")[0].strip("[]") if message else ""
            events.append(EventData(
                occurred_at=parse_datetime(ev.get("timestamp") or None),
                status_key=_clean(ev.get("status")),
                status_label=message,
                location=head,
                raw=ev,
            ))
        status = _clean(raw.get("current_status"))
        events.sort(key=lambda e: e.occurred_at or datetime.min, reverse=True)
        return NormalizedPayload(
            tracking_code=raw.get("sls_tracking_number", ""),
            status_code=status,
            status_label=status,
            location=events[0].location if events else "",
            last_event_at=events[0].occurred_at if events else None,
            estimated_delivery=None,
            is_terminal="delivered" in status.lower(),
            events=events,
            raw=raw,
        )


class AnjunAdapter(BaseAdapter):
    nid = CARRIER_ANJUN
    name = "Anjun Express"
    host_path = "/anjun"

    def normalize(self, raw: dict) -> NormalizedPayload:
        nodes = raw.get("nodeDataList", []) or []
        events = []
        for ev in nodes:
            events.append(EventData(
                occurred_at=parse_datetime(_clean(ev.get("dateTime"))),
                status_key=_clean(ev.get("statusCode")),
                status_label=_clean(ev.get("signTypeName") or ev.get("status")),
                location=_clean(ev.get("address")),
                raw=ev,
            ))
        status = _clean(raw.get("lastTrackStatus"))
        events.sort(key=lambda e: e.occurred_at or datetime.min, reverse=True)
        return NormalizedPayload(
            tracking_code=raw.get("trackNo", ""),
            status_code=status,
            status_label=events[0].status_label if events else "",
            location=events[0].location if events else "",
            last_event_at=events[0].occurred_at if events else None,
            estimated_delivery=None,
            is_terminal="signed" in status.lower(),
            events=events,
            raw=raw,
        )


class JTExpressAdapter(BaseAdapter):
    nid = CARRIER_JTEXPRESS
    name = "J&T Express"
    host_path = "/jtexpress"
    requires_document = True

    def normalize(self, raw: dict) -> NormalizedPayload:
        details = raw.get("details", [])
        events = []
        for ev in details:
            events.append(EventData(
                occurred_at=parse_datetime(_clean(ev.get("scanTime"))),
                status_key=str(ev.get("code", "")),
                status_label=_clean(ev.get("status") or ev.get("scanTypeName")),
                location=_clean(ev.get("customerTracking")),
                raw=ev,
            ))
        is_terminal = any(str(e.get("code", "")).strip() == "100" for e in details)
        events.sort(key=lambda e: e.occurred_at or datetime.min, reverse=True)
        return NormalizedPayload(
            tracking_code=raw.get("keyword", ""),
            status_code=events[0].status_key if events else "",
            status_label=events[0].status_label if events else "",
            location=events[0].location if events else "",
            last_event_at=events[0].occurred_at if events else None,
            estimated_delivery=None,
            is_terminal=is_terminal,
            events=events,
            raw=raw,
        )


class TotalExpressAdapter(BaseAdapter):
    nid = CARRIER_TOTALEXPRESS
    name = "Total Express"
    host_path = "/totalexpress"
    TERMINAL_STATID = {"1", "104"}

    def normalize(self, raw: dict) -> NormalizedPayload:
        data = raw.get("data", {})
        encomenda = data.get("encomenda", {})
        events = []
        is_terminal = False
        for layout in data.get("layouts", []):
            for etapa in layout.get("etapas", []):
                for st in etapa.get("listaStatus", []):
                    status_id = str(st.get("statid", "")).strip()
                    desc = _clean(st.get("statusDescricao"))
                    if status_id in self.TERMINAL_STATID or "entrega realizada" in desc.lower():
                        is_terminal = True
                    events.append(EventData(
                        occurred_at=parse_datetime(f"{st.get('data')} {st.get('hora')}".strip()),
                        status_key=status_id,
                        status_label=desc,
                        location="",
                        raw=st,
                    ))
        events.sort(key=lambda e: e.occurred_at or datetime.min, reverse=True)
        return NormalizedPayload(
            tracking_code=encomenda.get("awb", ""),
            status_code=str(encomenda.get("ultimoStatusId", "")),
            status_label=events[0].status_label if events else "",
            location="",
            last_event_at=events[0].occurred_at if events else None,
            estimated_delivery=parse_date(_clean(encomenda.get("previsaoEntrega"))),
            is_terminal=is_terminal,
            events=events,
            raw=raw,
        )


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
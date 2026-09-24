from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PT_BR_TZ = ZoneInfo("America/Sao_Paulo")

_ISO_WITH_WS = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"]
_DMY_WITH_WS = ["%d-%m-%Y %H:%M:%S"]


def parse_datetime(value):
    """Converte formatos comuns dos carriers para datetime aware (fuso America/Sao_Paulo).

    Timestamps ISO (com T) do PacoteVício são RFC 3339 em UTC: o sufixo 'Z' é aceito,
    offsets explícitos são preservados e valores sem fuso são assumidos como UTC.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        seconds = value
        if abs(seconds) > 10_000_000_000:
            seconds = seconds / 1000
        return datetime.fromtimestamp(seconds, tz=PT_BR_TZ)
    text = str(value).strip()
    for fmt in _ISO_WITH_WS:
        try:
            return to_aware(datetime.strptime(text, fmt))
        except ValueError:
            continue
    for fmt in _DMY_WITH_WS:
        try:
            return to_aware(datetime.strptime(text, fmt))
        except ValueError:
            continue
    if "T" in text:
        text = text.replace("Z", "+00:00", 1) if text.endswith("Z") else text
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return None


def parse_date(value):
    if value is None or value == "":
        return None
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def to_aware(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=PT_BR_TZ)
    return dt
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum

from django.conf import settings
from django.core.mail import send_mail
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from apps.carriers.adapters import get_adapter, normalize_v1
from apps.carriers.client import PacoteVicioClient
from apps.carriers.exceptions import PacoteVicioClientError, PacoteVicioServerError
from apps.core.models import SyncLog
from apps.trackings.models import (
    STATE_DELIVERED,
    STATE_IN_TRANSIT,
    Package,
    TrackingEvent,
)

logger = logging.getLogger(__name__)

PERMANENT_CLIENT_ERROR_CODES = {"invalid_tracking_code", "courier_not_supported"}


class SyncResult(Enum):
    OK = "ok"
    ERROR = "erro"
    PAUSED = "pausado"
    NO_DOCUMENT = "sem_documento"


def _package_url(package: Package) -> str:
    base = getattr(settings, "PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not base:
        return ""
    try:
        return f"{base}{reverse('package_detail', kwargs={'tracking_code': package.tracking_code})}"
    except Exception:  # noqa: BLE001
        return ""


def _notify(package: Package, subject: str, body: str) -> None:
    to = getattr(settings, "PACOTE_NOTIFY_EMAIL", "").strip()
    if not to:
        return
    url = _package_url(package)
    if url:
        body = f"{body}\nAcompanhe: {url}"
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=True)


def _apply_events(package: Package, normalized) -> None:
    prev_state = package.state
    prev_is_delayed = package.is_delayed
    new_events = []
    for ev in sorted(normalized.events, key=lambda e: (e.occurred_at is None, e.occurred_at or timezone.now())):
        fp = TrackingEvent.make_fingerprint(package.id, ev.occurred_at, ev.status_key, ev.status_label)
        new_events.append(TrackingEvent(
            package=package,
            fingerprint=fp,
            occurred_at=ev.occurred_at,
            status_key=ev.status_key,
            status_label=ev.status_label,
            location=ev.location,
            raw=ev.raw,
        ))
    TrackingEvent.objects.bulk_create(new_events, ignore_conflicts=True)
    package.status_code = normalized.status_code
    package.status_label = normalized.status_label
    package.location = normalized.location
    package.last_event_at = normalized.last_event_at
    package.estimated_delivery = normalized.estimated_delivery
    package.last_raw = normalized.raw
    package.last_error = ""
    now = timezone.now()
    if normalized.is_terminal:
        package.mark_terminal(normalized.status_code, normalized.terminal_state or STATE_DELIVERED)
        package.last_raw = {}
    if package.state == STATE_IN_TRANSIT and package.estimated_delivery and package.estimated_delivery < timezone.localdate():
        package.is_delayed = True
    if normalized.is_terminal and prev_state != STATE_DELIVERED and not package.delivered_notified_at:
        package.delivered_notified_at = now
        _notify(package, f"Entregue: {package.display_code}", f"Sua encomenda {package.display_code} foi entregue/encerrada.")
    if package.is_delayed and not prev_is_delayed and not package.delay_notified_at:
        package.delay_notified_at = now
        _notify(package, f"Possível atraso: {package.display_code}", f"Encomenda {package.display_code} ultrapassou a previsão de entrega.")
    package.last_synced_at = now
    package.save()


def sync_package(package: Package, client: PacoteVicioClient | None = None) -> SyncResult:
    if SyncLog.is_paused():
        package.last_error = "Cota diária atingida — sincronização pausada."
        package.save(update_fields=["last_error"])
        return SyncResult.PAUSED
    client = client or PacoteVicioClient()
    adapter = get_adapter(package.carrier)
    if adapter.requires_document and not package.document:
        package.last_error = "A J&T Express exige o CPF ou CNPJ do destinatário (campo 'document')."
        package.save(update_fields=["last_error"])
        return SyncResult.NO_DOCUMENT
    try:
        raw = client.fetch(adapter.nid, package.tracking_code, package.document)
        SyncLog.increment()
    except PacoteVicioClientError as exc:
        package.last_error = f"Erro {exc.status_code} ({exc.code or 'sem código'}): {exc}"
        if exc.code in PERMANENT_CLIENT_ERROR_CODES:
            package.is_active = False
            package.save(update_fields=["last_error", "is_active", "updated_at"])
        else:
            package.save(update_fields=["last_error"])
        return SyncResult.ERROR
    except PacoteVicioServerError as exc:
        package.last_error = f"Falha temporária: {exc}"
        package.save(update_fields=["last_error"])
        return SyncResult.ERROR
    normalized = normalize_v1(raw)
    _apply_events(package, normalized)
    return SyncResult.OK


def _sync_one(package: Package, client: PacoteVicioClient) -> SyncResult:
    try:
        return sync_package(package, client)
    except Exception as exc:  # noqa: BLE001 - isolar falhas inesperadas do lote
        logger.exception("Falha inesperada ao sincronizar %s", package.tracking_code)
        package.last_error = f"Falha inesperada: {exc}"
        package.save(update_fields=["last_error", "updated_at"])
        return SyncResult.ERROR


def sync_all(client: PacoteVicioClient | None = None) -> dict:
    client = client or PacoteVicioClient()
    results = {"ok": 0, "erro": 0, "pausado": 0, "sem_documento": 0}
    packages = list(Package.objects.filter(is_active=True))
    workers = getattr(settings, "SYNC_WORKERS", 4)
    if workers <= 1 or len(packages) <= 1 or connection.vendor == "sqlite":
        for package in packages:
            res = _sync_one(package, client)
            results[res.value] += 1
        return results
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_sync_one, package, client) for package in packages]
        for future in as_completed(futures):
            res = future.result()
            results[res.value] += 1
    return results
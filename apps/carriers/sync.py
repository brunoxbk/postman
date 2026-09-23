from django.utils import timezone

from apps.carriers.adapters import get_adapter
from apps.carriers.client import PacoteVicioClient
from apps.carriers.exceptions import PacoteVicioClientError, PacoteVicioServerError
from apps.core.models import SyncLog
from apps.trackings.models import (
    Package,
    TrackingEvent,
    STATE_DELIVERED,
)


def _apply_events(package: Package, normalized) -> None:
    for ev in sorted(normalized.events, key=lambda e: (e.occurred_at is None, e.occurred_at or timezone.now())):
        fp = TrackingEvent.make_fingerprint(package.id, ev.occurred_at, ev.status_key, ev.status_label)
        TrackingEvent.objects.get_or_create(
            package=package, fingerprint=fp,
            defaults={
                "occurred_at": ev.occurred_at,
                "status_key": ev.status_key,
                "status_label": ev.status_label,
                "location": ev.location,
                "raw": ev.raw,
            },
        )
    package.status_code = normalized.status_code
    package.status_label = normalized.status_label
    package.location = normalized.location
    package.last_event_at = normalized.last_event_at
    package.estimated_delivery = normalized.estimated_delivery
    package.last_raw = normalized.raw
    package.last_error = ""
    if normalized.is_terminal:
        package.mark_terminal(normalized.status_code, STATE_DELIVERED)
    if package.state == "in_transit" and package.estimated_delivery and package.estimated_delivery < timezone.localdate():
        package.is_delayed = True
    package.last_synced_at = timezone.now()
    package.save()


def sync_package(package: Package, client: PacoteVicioClient | None = None) -> bool | None:
    if SyncLog.is_paused():
        package.last_error = "Cota mensal atingida — sincronização pausada."
        package.save(update_fields=["last_error"])
        return None
    client = client or PacoteVicioClient()
    adapter = get_adapter(package.carrier)
    if adapter.requires_document and not package.document:
        package.last_error = "J&T Express exige o CPF do destinatário (campo 'document')."
        package.save(update_fields=["last_error"])
        return False
    params = adapter.build_params(package.tracking_code, package.document)
    try:
        raw = client.fetch(adapter.host_path, params)
        SyncLog.increment()
    except PacoteVicioClientError as exc:
        package.last_error = f"Erro {exc.status_code}: {exc}"
        package.save(update_fields=["last_error"])
        return False
    except PacoteVicioServerError as exc:
        package.last_error = f"Falha temporária: {exc}"
        package.save(update_fields=["last_error"])
        return False
    normalized = adapter.normalize(raw)
    _apply_events(package, normalized)
    return True


def sync_all(client: PacoteVicioClient | None = None) -> dict:
    client = client or PacoteVicioClient()
    results = {"ok": 0, "erro": 0, "pausado": 0, "sem_documento": 0}
    for package in Package.objects.filter(is_active=True):
        res = sync_package(package, client)
        if res is True:
            results["ok"] += 1
        elif res is False:
            if "CPF" in package.last_error:
                results["sem_documento"] += 1
            else:
                results["erro"] += 1
        else:
            results["pausado"] += 1
    return results
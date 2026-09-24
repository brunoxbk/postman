import logging
import threading

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.carriers.sync import pending_packages, sync_all, sync_package
from apps.core.models import SyncLog
from apps.trackings.forms import PackageForm
from apps.trackings.models import (
    STATE_DELIVERED,
    STATE_IN_TRANSIT,
    Package,
)

logger = logging.getLogger(__name__)

SORTS = {
    "created": "-created_at",
    "last_event": "-last_event_at",
    "eta": "estimated_delivery",
    "carrier": "carrier",
    "state": "state",
}


def _dashboard_context(request):
    qs = Package.objects.all().defer("last_raw")
    q = request.GET.get("q", "").strip()
    carrier = request.GET.get("carrier", "").strip()
    raw_state = request.GET.get("state")
    state = STATE_IN_TRANSIT if raw_state is None else raw_state.strip()
    sort = request.GET.get("sort", "created").strip()
    if q:
        qs = qs.filter(Q(tracking_code__icontains=q) | Q(label__icontains=q))
    if carrier:
        qs = qs.filter(carrier=carrier)
    if state:
        qs = qs.filter(state=state)
    order = SORTS.get(sort) or SORTS["created"]
    paginator = Paginator(qs.order_by(order, "-created_at"), 25)
    page_obj = paginator.get_page(request.GET.get("page", "1"))
    today = timezone.localdate()
    counts = Package.objects.aggregate(
        count_in_transit=Count("id", filter=Q(state=STATE_IN_TRANSIT)),
        count_delivered=Count("id", filter=Q(state=STATE_DELIVERED)),
        count_delayed=Count("id", filter=Q(state=STATE_IN_TRANSIT, estimated_delivery__lt=today)),
    )
    last_synced_at = (
        Package.objects.filter(last_synced_at__isnull=False)
        .order_by("-last_synced_at")
        .values_list("last_synced_at", flat=True)
        .first()
    )
    return {
        "page_obj": page_obj,
        "packages": page_obj.object_list,
        **counts,
        "quota": {
            "used": SyncLog.count_period(),
            "limit": getattr(settings, "COTA_MENSAL", 1000),
        },
        "last_synced_at": last_synced_at,
        "filter_q": q, "filter_carrier": carrier, "filter_state": state, "filter_sort": sort,
    }


@login_required
def dashboard(request):
    return render(request, "dashboard.html", _dashboard_context(request))


@login_required
def dashboard_blocks(request):
    return render(request, "dashboard_blocks.html", _dashboard_context(request))


@login_required
def package_new(request):
    form = PackageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Encomenda cadastrada!")
        return redirect("dashboard")
    return render(request, "package_form.html", {"form": form, "title": "Nova encomenda"})


@login_required
def package_edit(request, tracking_code):
    package = get_object_or_404(Package, tracking_code__iexact=tracking_code)
    form = PackageForm(request.POST or None, instance=package)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Encomenda atualizada!")
        return redirect("package_detail", tracking_code=package.tracking_code)
    return render(request, "package_form.html", {"form": form, "title": f"Editar {package.tracking_code}"})


@login_required
def package_detail(request, tracking_code):
    package = get_object_or_404(Package, tracking_code__iexact=tracking_code)
    events = package.events.all()
    return render(request, "package_detail.html", {"package": package, "events": events})


def _run_sync_in_background(package_id: int) -> None:
    try:
        package = Package.objects.get(pk=package_id)
        sync_package(package)
    except Package.DoesNotExist:
        logger.warning("Encomenda %s não existe mais — sync ignorado.", package_id)
    finally:
        connection.close()


def spawn_background_sync(package: Package) -> threading.Thread:
    thread = threading.Thread(
        target=_run_sync_in_background,
        args=(package.pk,),
        daemon=True,
        name=f"sync-{package.pk}",
    )
    thread.start()
    return thread


def _run_sync_all_in_background() -> None:
    try:
        sync_all()
    finally:
        connection.close()


def spawn_background_sync_all() -> threading.Thread:
    thread = threading.Thread(
        target=_run_sync_all_in_background,
        daemon=True,
        name="sync-all",
    )
    thread.start()
    return thread


@login_required
@require_POST
def sync_all_now(request):
    if SyncLog.is_paused():
        messages.warning(request, "Cota mensal atingida — sincronização pausada.")
    else:
        pending = pending_packages().count()
        spawn_background_sync_all()
        messages.success(
            request,
            f"Sincronização iniciada em segundo plano para {pending} encomenda(s) desatualizada(s).",
        )
    return redirect("dashboard")


@login_required
@require_POST
def package_sync_now(request, tracking_code):
    package = get_object_or_404(Package, tracking_code__iexact=tracking_code)
    if SyncLog.is_paused():
        messages.warning(request, "Cota mensal atingida — sincronização pausada.")
    else:
        spawn_background_sync(package)
        messages.success(
            request,
            "Sincronização iniciada em segundo plano — os dados aparecem na próxima atualização.",
        )
    return redirect("package_detail", tracking_code=package.tracking_code)


@login_required
@require_POST
def package_reactivate(request, tracking_code):
    package = get_object_or_404(Package, tracking_code__iexact=tracking_code)
    if package.is_active:
        messages.info(request, "A encomenda já está ativa.")
    else:
        package.is_active = True
        package.state = STATE_IN_TRANSIT
        package.is_delayed = False
        package.last_error = ""
        package.save(update_fields=["is_active", "state", "is_delayed", "last_error"])
        messages.success(request, "Rastreio reaberto — as próximas sincronizações voltarão a consultar.")
    return redirect("package_detail", tracking_code=package.tracking_code)


@login_required
def package_delete(request, tracking_code):
    package = get_object_or_404(Package, tracking_code__iexact=tracking_code)
    if request.method == "POST":
        package.delete()
        messages.success(request, "Encomenda excluída.")
        return redirect("dashboard")
    return render(request, "package_confirm_delete.html", {"package": package})
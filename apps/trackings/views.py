from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.carriers.sync import sync_package
from apps.core.models import SyncLog
from apps.trackings.forms import PackageForm
from apps.trackings.models import (
    Package,
    STATE_IN_TRANSIT,
    STATE_DELIVERED,
)


@login_required
def dashboard(request):
    qs = Package.objects.all()
    q = request.GET.get("q", "").strip()
    carrier = request.GET.get("carrier", "").strip()
    state = request.GET.get("state", "").strip()
    if q:
        qs = qs.filter(tracking_code__icontains=q)
    if carrier:
        qs = qs.filter(carrier=carrier)
    if state:
        qs = qs.filter(state=state)
    paginator = Paginator(qs.select_related(), 25)
    page_obj = paginator.get_page(request.GET.get("page", "1"))
    today = timezone.localdate()
    for p in page_obj:
        p.is_delayed = (
            p.state == STATE_IN_TRANSIT
            and p.estimated_delivery is not None
            and p.estimated_delivery < today
        )
    last_synced_at = (
        Package.objects.filter(last_synced_at__isnull=False)
        .order_by("-last_synced_at")
        .values_list("last_synced_at", flat=True)
        .first()
    )
    ctx = {
        "page_obj": page_obj,
        "packages": page_obj.object_list,
        "count_in_transit": Package.objects.filter(state=STATE_IN_TRANSIT).count(),
        "count_delivered": Package.objects.filter(state=STATE_DELIVERED).count(),
        "count_delayed": Package.objects.filter(state=STATE_IN_TRANSIT, estimated_delivery__lt=today).count(),
        "quota": {
            "used": SyncLog.count_today(),
            "limit": getattr(settings, "COTA_MENSAL", 900),
        },
        "last_synced_at": last_synced_at,
        "filter_q": q, "filter_carrier": carrier, "filter_state": state,
    }
    return render(request, "dashboard.html", ctx)


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


@login_required
@require_POST
def package_sync_now(request, tracking_code):
    package = get_object_or_404(Package, tracking_code__iexact=tracking_code)
    result = sync_package(package)
    if result is None:
        messages.warning(request, "Cota mensal atingida — sincronização pausada.")
    elif result is False:
        messages.error(request, package.last_error or "Erro ao sincronizar.")
    else:
        messages.success(request, "Sincronização executada.")
    return redirect("package_detail", tracking_code=package.tracking_code)


@login_required
def package_delete(request, tracking_code):
    package = get_object_or_404(Package, tracking_code__iexact=tracking_code)
    if request.method == "POST":
        package.delete()
        messages.success(request, "Encomenda excluída.")
        return redirect("dashboard")
    return render(request, "package_confirm_delete.html", {"package": package})
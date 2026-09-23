from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.carriers.sync import sync_package
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
    packages = list(qs.select_related()[:200])
    today = timezone.localdate()
    for p in packages:
        p.is_delayed = (
            p.state == STATE_IN_TRANSIT
            and p.estimated_delivery is not None
            and p.estimated_delivery < today
        )
    ctx = {
        "packages": packages,
        "count_in_transit": Package.objects.filter(state=STATE_IN_TRANSIT).count(),
        "count_delivered": Package.objects.filter(state=STATE_DELIVERED).count(),
        "count_delayed": Package.objects.filter(state=STATE_IN_TRANSIT, estimated_delivery__lt=today).count(),
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
def package_sync_now(request, tracking_code):
    package = get_object_or_404(Package, tracking_code__iexact=tracking_code)
    sync_package(package)
    messages.info(request, "Sincronização executada.")
    return redirect("package_detail", tracking_code=package.tracking_code)


@login_required
def package_delete(request, tracking_code):
    package = get_object_or_404(Package, tracking_code__iexact=tracking_code)
    if request.method == "POST":
        package.delete()
        messages.success(request, "Encomenda excluída.")
        return redirect("dashboard")
    return render(request, "package_confirm_delete.html", {"package": package})
import hashlib

from django.db import migrations


def _fingerprint(package_id, occurred_at, status_key, status_label):
    stamp = occurred_at.isoformat() if occurred_at else ""
    base = f"{package_id};{stamp};{status_key};{status_label}".lower()
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def normalize_tracking_codes(apps, schema_editor):
    Package = apps.get_model("trackings", "Package")
    TrackingEvent = apps.get_model("trackings", "TrackingEvent")

    groups = {}
    for package in Package.objects.all().order_by("id"):
        key = (package.tracking_code or "").strip().upper()
        groups.setdefault(key, []).append(package)

    for key, packages in groups.items():
        keeper = packages[0]
        for dup in packages[1:]:
            for event in TrackingEvent.objects.filter(package=dup):
                fp = _fingerprint(
                    keeper.id, event.occurred_at, event.status_key, event.status_label
                )
                if TrackingEvent.objects.filter(package=keeper, fingerprint=fp).exists():
                    event.delete()
                    continue
                event.package = keeper
                event.fingerprint = fp
                event.save()
            dup.delete()
        if keeper.tracking_code != key:
            keeper.tracking_code = key
            keeper.save(update_fields=["tracking_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("trackings", "0003_indexes_eta_and_last_event"),
    ]

    operations = [
        migrations.RunPython(normalize_tracking_codes, migrations.RunPython.noop),
    ]
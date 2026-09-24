from django.db.models import Prefetch
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_api_key.permissions import HasAPIKey

from apps.carriers.adapters import detect_carrier, is_plausible_code
from apps.carriers.constants import CARRIER_CHOICES
from apps.carriers.sync import SyncResult, sync_package
from apps.trackings.models import Package, TrackingEvent

SYNC_STATUS = {
    SyncResult.OK: True,
    SyncResult.ERROR: False,
    SyncResult.NO_DOCUMENT: False,
    SyncResult.PAUSED: None,
}


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackingEvent
        fields = ("occurred_at", "status_key", "status_label", "location")


class PackageSerializer(serializers.ModelSerializer):
    events = EventSerializer(many=True, read_only=True)
    carrier_display = serializers.CharField(source="get_carrier_display", read_only=True)
    carrier = serializers.ChoiceField(choices=CARRIER_CHOICES, required=False, allow_blank=True)
    document = serializers.CharField(
        max_length=16, required=False, allow_blank=True, write_only=True,
        style={"input_type": "text"},
    )

    class Meta:
        model = Package
        fields = (
            "tracking_code", "carrier", "carrier_display", "label", "document",
            "status_code", "status_label", "location", "last_event_at",
            "estimated_delivery", "state", "is_active", "is_delayed",
            "last_synced_at", "last_error", "created_at", "events",
        )

    def validate_tracking_code(self, value):
        value = value.strip().upper()
        qs = Package.objects.filter(tracking_code__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Código já cadastrado.")
        return value

    def create(self, validated_data):
        code = validated_data.get("tracking_code", "")
        carrier = validated_data.get("carrier") or ""
        detected = detect_carrier(code)
        if not detected:
            if not carrier or not is_plausible_code(code):
                raise serializers.ValidationError(
                    {"tracking_code": "Não foi possível identificar a transportadora pelo código."}
                )
            validated_data["carrier"] = carrier
            return super().create(validated_data)
        validated_data["carrier"] = carrier or detected
        return super().create(validated_data)


class PackageViewSet(viewsets.ModelViewSet):
    serializer_class = PackageSerializer
    permission_classes = [HasAPIKey]
    lookup_field = "tracking_code"

    def get_queryset(self):
        qs = Package.objects.all().defer("last_raw")
        code = self.request.query_params.get("q")
        carrier = self.request.query_params.get("carrier")
        state = self.request.query_params.get("state")
        if code:
            qs = qs.filter(tracking_code__icontains=code)
        if carrier:
            qs = qs.filter(carrier=carrier)
        if state:
            qs = qs.filter(state=state)
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        recent_ids = TrackingEvent.objects.order_by("-occurred_at", "-id").values_list("pk", flat=True)[:50]
        page = self.paginate_queryset(
            queryset.prefetch_related(
                Prefetch("events", queryset=TrackingEvent.objects.filter(pk__in=recent_ids))
            )
        )
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["POST"])
    def sync(self, request, tracking_code=None):
        package = self.get_object()
        result = sync_package(package)
        package.refresh_from_db()
        serializer = self.get_serializer(package)
        return Response({"sync_status": SYNC_STATUS[result], "package": serializer.data})
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_api_key.permissions import HasAPIKey

from apps.carriers.adapters import detect_carrier
from apps.carriers.constants import CARRIER_CHOICES
from apps.carriers.sync import sync_package
from apps.trackings.models import Package, TrackingEvent


class HealthView(APIView):
    permission_classes = [HasAPIKey]

    def get(self, request):
        return Response({"status": "ok"})


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackingEvent
        fields = ("occurred_at", "status_key", "status_label", "location", "raw")


class PackageSerializer(serializers.ModelSerializer):
    events = EventSerializer(many=True, read_only=True)
    carrier_display = serializers.CharField(source="get_carrier_display", read_only=True)
    carrier = serializers.ChoiceField(choices=CARRIER_CHOICES, required=False, allow_blank=True)

    class Meta:
        model = Package
        fields = (
            "tracking_code", "carrier", "carrier_display", "label", "status_code",
            "status_label", "location", "last_event_at", "estimated_delivery",
            "state", "is_active", "is_delayed", "last_synced_at", "last_error",
            "created_at", "events",
        )

    def validate_tracking_code(self, value):
        value = value.strip()
        if Package.objects.filter(tracking_code__iexact=value).exists():
            raise serializers.ValidationError("Código já cadastrado.")
        return value

    def create(self, validated_data):
        code = validated_data.get("tracking_code", "")
        carrier = validated_data.get("carrier") or detect_carrier(code) or ""
        if not carrier:
            raise serializers.ValidationError(
                {"carrier": "Não foi possível identificar a transportadora pelo código."}
            )
        validated_data["carrier"] = carrier
        return super().create(validated_data)


class PackageViewSet(viewsets.ModelViewSet):
    serializer_class = PackageSerializer
    permission_classes = [HasAPIKey]
    lookup_field = "tracking_code"

    def get_queryset(self):
        qs = Package.objects.all()
        code = self.request.query_params.get("q")
        carrier = self.request.query_params.get("carrier")
        state = self.request.query_params.get("state")
        if code:
            qs = qs.filter(tracking_code__icontains=code)
        if carrier:
            qs = qs.filter(carrier=carrier)
        if state:
            qs = qs.filter(state=state)
        return qs.select_related().prefetch_related("events")

    @action(detail=True, methods=["POST"])
    def sync(self, request, tracking_code=None):
        package = self.get_object()
        result = sync_package(package)
        package.refresh_from_db()
        serializer = self.get_serializer(package)
        return Response({"sync_status": result, "package": serializer.data})
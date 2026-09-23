from rest_framework import serializers, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_api_key.permissions import HasAPIKey

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
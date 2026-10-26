from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsOwnerOrAdmin
from .models import LaborPayment, Settlement, SettlementDetailHarvest, SettlementDetailWorkday
from .serializers import (
    AddHarvestDetailSerializer,
    AddWorkdayDetailSerializer,
    CloseSettlementSerializer,
    LaborPaymentSerializer,
    PaySettlementSerializer,
    SettlementDetailHarvestSerializer,
    SettlementDetailWorkdaySerializer,
    SettlementSerializer,
)
from .services import PayrollService


# ---------------------------------------------------------------------------
# VIEWSETS - SOLO RECIBEN, INVOCAN SERVICIO Y RESPONDEN
# ---------------------------------------------------------------------------


class BasePayrollViewSet(viewsets.ModelViewSet):
    """Base con auth y permisos."""
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]


class SettlementViewSet(BasePayrollViewSet):
    """CRUD de liquidaciones + acciones delegadas a servicios."""
    serializer_class = SettlementSerializer
    queryset = (
        Settlement.objects.select_related("worker", "farm")
        .prefetch_related("workday_details", "harvest_details", "payment")
        .all()
    )

    def get_queryset(self):
        # Filtra por productor o todo si es admin
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, "is_administrator", False):
            return queryset
        return queryset.filter(worker__producer=user)

    def perform_create(self, serializer):
        # Fuerza pertenencia al productor
        user = self.request.user
        worker = serializer.validated_data.get("worker")
        if worker and not getattr(user, "is_administrator", False) and worker.producer != user:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("No puedes crear liquidaciones para trabajadores ajenos.")
        serializer.save()

    @action(detail=False, methods=["post"], url_path="add-workday")
    def add_workday(self, request):
        """Añade jornada por jornal via servicio."""
        serializer = AddWorkdayDetailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            detail = PayrollService.add_workday_to_settlement(
                settlement_id=data["settlement_id"],
                workday_id=data["workday_id"],
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            SettlementDetailWorkdaySerializer(detail).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="add-harvest")
    def add_harvest(self, request):
        """Añade pesaje por kg via servicio."""
        serializer = AddHarvestDetailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            detail = PayrollService.add_harvest_to_settlement(
                settlement_id=data["settlement_id"],
                harvest_record_id=data["harvest_record_id"],
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            SettlementDetailHarvestSerializer(detail).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="close")
    def close(self, request):
        """Cierra liquidación via servicio."""
        serializer = CloseSettlementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            settlement = PayrollService.close_settlement(
                settlement_id=data["settlement_id"]
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SettlementSerializer(settlement).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="pay")
    def pay(self, request):
        """Registra pago via servicio."""
        serializer = PaySettlementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            payment = PayrollService.pay_settlement(
                settlement_id=data["settlement_id"],
                date=data["date"],
                amount_paid=data["amount_paid"],
                payment_method=data["payment_method"],
                notes=data.get("notes", ""),
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LaborPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class SettlementDetailWorkdayViewSet(BasePayrollViewSet):
    """Consulta detalles por jornal."""
    serializer_class = SettlementDetailWorkdaySerializer
    queryset = SettlementDetailWorkday.objects.select_related(
        "settlement", "workday", "settlement__worker__producer"
    ).all()

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, "is_administrator", False):
            return queryset
        return queryset.filter(settlement__worker__producer=user)


class SettlementDetailHarvestViewSet(BasePayrollViewSet):
    """Consulta detalles por kg."""
    serializer_class = SettlementDetailHarvestSerializer
    queryset = SettlementDetailHarvest.objects.select_related(
        "settlement", "harvest_record", "settlement__worker__producer"
    ).all()

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, "is_administrator", False):
            return queryset
        return queryset.filter(settlement__worker__producer=user)


class LaborPaymentViewSet(BasePayrollViewSet):
    """Consulta pagos laborales."""
    serializer_class = LaborPaymentSerializer
    queryset = LaborPayment.objects.select_related(
        "settlement", "settlement__worker__producer"
    ).all()

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, "is_administrator", False):
            return queryset
        return queryset.filter(settlement__worker__producer=user)

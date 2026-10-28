from uuid import UUID

from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.exceptions import MethodNotAllowed, ValidationError
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import IsOwnerOrAdmin

from .models import OperatingExpense
from .serializers import OperatingExpenseSerializer


class OperatingExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = OperatingExpenseSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
    queryset = OperatingExpense.objects.select_related(
        "farm", "farm__id_productor", "labor_payment"
    ).all()

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if not getattr(user, "is_administrator", False):
            queryset = queryset.filter(farm__id_productor=user)

        params = self.request.query_params
        category = params.get("category")
        if category:
            valid_categories = dict(OperatingExpense.Category.choices)
            if category not in valid_categories:
                raise ValidationError({"category": "La categoría no es válida."})
            queryset = queryset.filter(category=category)

        farm_id = params.get("farm")
        if farm_id:
            try:
                farm_id = UUID(farm_id)
            except ValueError:
                raise ValidationError({"farm": "El identificador de finca no es válido."})
            queryset = queryset.filter(farm_id=farm_id)

        date_from = self._parse_date_param(params, "date_from")
        date_to = self._parse_date_param(params, "date_to")
        if date_from and date_to and date_from > date_to:
            raise ValidationError(
                {"date_to": "La fecha final no puede ser anterior a la fecha inicial."}
            )
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        return queryset

    @staticmethod
    def _parse_date_param(params, name):
        value = params.get(name)
        if value is None:
            return None
        parsed_date = parse_date(value)
        if parsed_date is None:
            raise ValidationError({name: "Usa una fecha válida con formato AAAA-MM-DD."})
        return parsed_date

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed(
            "DELETE",
            detail="Los egresos se conservan para mantener el historial financiero.",
        )

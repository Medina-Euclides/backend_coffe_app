from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from apps.farms.models import Farm, Lot
from .models import (
    Worker,
    ActivityType,
    Workday,
    WorkdayWorker,
    WorkdayDetail,
    HarvestRecord,
)

User = get_user_model()


class WorkerSerializer(serializers.ModelSerializer):
    """
    Serializador para los trabajadores contratados por el productor.
    Reglas de negocio aplicadas:
      - Sección 2, Regla 1: 'El productor registra a cada trabajador una sola vez.'
      - Sección 2, Regla 2: 'Un trabajador puede realizar labores en distintas fincas del mismo productor.'
      - Sección 2, Regla 4: 'Los trabajadores inactivos deben conservar sus registros históricos.'
    """

    producer = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False
    )
    producer_name = serializers.CharField(source="producer.full_name", read_only=True)
    producer_email = serializers.EmailField(source="producer.email", read_only=True)

    class Meta:
        model = Worker
        fields = (
            'id', 'producer', 'producer_name', 'producer_email',
            'identification', 'first_name', 'last_name', 'phone', 'is_active',
            'created_at'
        )
        read_only_fields = ('id', 'created_at')

    def validate_producer(self, value):
        """
        Valida que un productor regular solo pueda registrar trabajadores a su propio nombre.
        Los administradores pueden asignar trabajadores a cualquier productor.
        """
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and not getattr(user, 'is_administrator', False):
            if value != user:
                raise serializers.ValidationError("Solo puedes registrar trabajadores a tu nombre.")
        return value


class ActivityTypeSerializer(serializers.ModelSerializer):
    """
    Serializador para los tipos de actividad laboral (limpieza, recolección, abonado, etc.).
    Reglas de negocio aplicadas:
      - Sección 3, Regla 1 y 2: 'El productor puede crear y modificar sus tipos de actividad, sin catálogo fijo.'
      - Sección 3, Regla 5: 'Las actividades de recolección deben distinguirse de las demás porque admiten dos modalidades de pago.'
    """

    producer = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False
    )

    class Meta:
        model = ActivityType
        fields = ('id', 'producer', 'name', 'description', 'is_harvest')
        read_only_fields = ('id',)

    def validate_producer(self, value):
        """
        Valida que un productor regular solo pueda registrar tipos de actividad para su propia cuenta.
        """
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and not getattr(user, 'is_administrator', False):
            if value != user:
                raise serializers.ValidationError("Solo puedes registrar actividades a tu nombre.")
        return value


class HarvestRecordSerializer(serializers.ModelSerializer):
    workday_detail = serializers.PrimaryKeyRelatedField(queryset=WorkdayDetail.objects.none())

    class Meta:
        model = HarvestRecord
        fields = ("id", "workday_detail", "quantity_kg", "time", "settlement_status")
        read_only_fields = ("id", "settlement_status")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        queryset = WorkdayDetail.objects.select_related(
            "activity_type",
            "workday_worker__workday",
        )
        if user and user.is_authenticated and not getattr(user, "is_administrator", False):
            queryset = queryset.filter(workday_worker__workday__producer=user)
        self.fields["workday_detail"].queryset = queryset

    def validate(self, attrs):
        attrs = super().validate(attrs)
        workday_detail = attrs.get(
            "workday_detail",
            getattr(self.instance, "workday_detail", None),
        )
        quantity = attrs.get("quantity_kg", getattr(self.instance, "quantity_kg", None))

        if workday_detail and not workday_detail.activity_type.is_harvest:
            raise serializers.ValidationError(
                {"workday_detail": "Solo se admiten pesajes en actividades de recolección."}
            )
        if quantity is not None and quantity <= 0:
            raise serializers.ValidationError(
                {"quantity_kg": "La cantidad recolectada debe ser mayor que cero."}
            )

        if self.instance is not None and self.instance.is_locked:
            raise serializers.ValidationError(
                {"detail": "No se puede modificar un pesaje liquidado o ya incluido en una liquidación."}
            )

        if workday_detail:
            participation = workday_detail.workday_worker
            if participation.workday.is_closed:
                raise serializers.ValidationError(
                    {"workday_detail": "No se pueden registrar pesajes en una jornada cerrada."}
                )
            if participation.is_locked:
                raise serializers.ValidationError(
                    {"workday_detail": "La participación ya fue liquidada o anulada."}
                )
        return attrs


class WorkdayDetailSerializer(serializers.ModelSerializer):
    harvest_records = HarvestRecordSerializer(many=True, read_only=True)
    workday_worker = serializers.PrimaryKeyRelatedField(queryset=WorkdayWorker.objects.none())
    activity_type = serializers.PrimaryKeyRelatedField(queryset=ActivityType.objects.none())
    lot = serializers.PrimaryKeyRelatedField(queryset=Lot.objects.none())
    activity_name = serializers.CharField(source="activity_type.name", read_only=True)
    activity_is_harvest = serializers.BooleanField(
        source="activity_type.is_harvest",
        read_only=True,
    )
    lot_name = serializers.CharField(source="lot.name", read_only=True)

    class Meta:
        model = WorkdayDetail
        fields = (
            "id",
            "workday_worker",
            "activity_type",
            "activity_name",
            "activity_is_harvest",
            "lot",
            "lot_name",
            "harvest_records",
        )
        read_only_fields = ("id",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated and not getattr(user, "is_administrator", False):
            self.fields["workday_worker"].queryset = WorkdayWorker.objects.filter(
                workday__producer=user
            )
            self.fields["activity_type"].queryset = ActivityType.objects.filter(producer=user)
            self.fields["lot"].queryset = Lot.objects.filter(id_farm__id_productor=user)
        else:
            self.fields["workday_worker"].queryset = WorkdayWorker.objects.all()
            self.fields["activity_type"].queryset = ActivityType.objects.all()
            self.fields["lot"].queryset = Lot.objects.all()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        workday_worker = attrs.get(
            "workday_worker",
            getattr(self.instance, "workday_worker", None),
        )
        activity_type = attrs.get(
            "activity_type",
            getattr(self.instance, "activity_type", None),
        )
        lot = attrs.get("lot", getattr(self.instance, "lot", None))

        if self.instance is not None:
            if self.instance.workday_worker.is_locked:
                raise serializers.ValidationError(
                    {"detail": "No se puede modificar un detalle de una participación liquidada o anulada."}
                )
            if self.instance.harvest_records.filter(settlement_status="liquidado").exists():
                raise serializers.ValidationError(
                    {"detail": "No se puede modificar un detalle con pesajes liquidados."}
                )

        if workday_worker:
            if workday_worker.workday.is_closed:
                raise serializers.ValidationError(
                    {"workday_worker": "No se pueden registrar detalles en una jornada cerrada."}
                )
            if workday_worker.is_locked:
                raise serializers.ValidationError(
                    {"workday_worker": "La participación ya fue liquidada o anulada."}
                )
            if self.instance is not None and self.instance.workday_worker_id != workday_worker.id:
                raise serializers.ValidationError(
                    {"workday_worker": "No se puede cambiar la participación de un detalle existente."}
                )

        if workday_worker and activity_type:
            producer_id = workday_worker.workday.producer_id
            if activity_type.producer_id != producer_id:
                raise serializers.ValidationError(
                    {"activity_type": "El tipo de actividad no pertenece al productor de la jornada."}
                )
            if (
                workday_worker.payment_mode == WorkdayWorker.PaymentMode.KILOGRAM
                and not activity_type.is_harvest
            ):
                raise serializers.ValidationError(
                    {"activity_type": "La modalidad por kilogramo solo admite actividades de recolección."}
                )

        if workday_worker and lot:
            if lot.id_farm_id != workday_worker.workday.farm_id:
                raise serializers.ValidationError(
                    {"lot": "El lote debe pertenecer a la finca de la jornada."}
                )
            if not lot.is_active:
                raise serializers.ValidationError(
                    {"lot": "No se pueden registrar labores en un lote inactivo."}
                )

        return attrs


class WorkdayWorkerSerializer(serializers.ModelSerializer):
    details = WorkdayDetailSerializer(many=True, read_only=True)
    worker_name = serializers.CharField(source="worker.__str__", read_only=True)
    worker_identification = serializers.CharField(
        source="worker.identification",
        read_only=True,
    )

    class Meta:
        model = WorkdayWorker
        fields = (
            "id",
            "workday",
            "worker",
            "worker_name",
            "worker_identification",
            "payment_mode",
            "agreed_rate",
            "settlement_status",
            "details",
        )
        read_only_fields = ("id", "settlement_status")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated and not getattr(user, "is_administrator", False):
            self.fields["worker"].queryset = Worker.objects.filter(producer=user)
            self.fields["workday"].queryset = Workday.objects.filter(producer=user)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        worker = attrs.get("worker", getattr(self.instance, "worker", None))
        workday = attrs.get("workday", getattr(self.instance, "workday", None))
        rate = attrs.get("agreed_rate", getattr(self.instance, "agreed_rate", None))
        payment_mode = attrs.get(
            "payment_mode",
            getattr(self.instance, "payment_mode", None),
        )

        if self.instance is not None and self.instance.is_locked:
            raise serializers.ValidationError(
                {"detail": "No se puede modificar una participación liquidada, anulada o incluida en una liquidación."}
            )

        if workday and workday.is_closed:
            raise serializers.ValidationError(
                {"workday": "No se pueden modificar participaciones de una jornada cerrada."}
            )

        if self.instance is not None:
            if "workday" in attrs and attrs["workday"].id != self.instance.workday_id:
                raise serializers.ValidationError(
                    {"workday": "No se puede cambiar la jornada de una participación existente."}
                )
            if "worker" in attrs and attrs["worker"].id != self.instance.worker_id:
                raise serializers.ValidationError(
                    {"worker": "No se puede cambiar el trabajador de una participación existente."}
                )
            if (
                payment_mode == WorkdayWorker.PaymentMode.KILOGRAM
                and self.instance.details.exclude(activity_type__is_harvest=True).exists()
            ):
                raise serializers.ValidationError(
                    {"payment_mode": "La modalidad por kilogramo no es compatible con los detalles ya registrados."}
                )
            if (
                payment_mode == WorkdayWorker.PaymentMode.DAILY
                and self.instance.details.filter(
                    harvest_records__isnull=False
                ).exists()
            ):
                raise serializers.ValidationError(
                    {"payment_mode": "La modalidad por jornal no es compatible con los pesajes ya registrados."}
                )

        if worker and not worker.is_active and (
            self.instance is None or worker.pk != self.instance.worker_id
        ):
            raise serializers.ValidationError(
                {"worker": "No se pueden crear participaciones para un trabajador inactivo."}
            )
        if worker and workday and worker.producer_id != workday.producer_id:
            raise serializers.ValidationError(
                {"worker": "El trabajador debe pertenecer al productor de la jornada."}
            )
        if rate is not None and rate <= 0:
            raise serializers.ValidationError(
                {"agreed_rate": "La tarifa acordada debe ser mayor que cero."}
            )
        return attrs


class WorkdaySerializer(serializers.ModelSerializer):
    participants = WorkdayWorkerSerializer(many=True, read_only=True)
    producer = serializers.PrimaryKeyRelatedField(read_only=True)
    farm = serializers.PrimaryKeyRelatedField(queryset=Farm.objects.none())
    farm_name = serializers.CharField(source="farm.name", read_only=True)

    class Meta:
        model = Workday
        fields = (
            "id", "producer", "farm", "farm_name", "date",
            "status", "closed_at", "created_at", "participants",
        )
        read_only_fields = ("id", "producer", "status", "closed_at", "created_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated and not getattr(user, "is_administrator", False):
            self.fields["farm"].queryset = Farm.objects.filter(id_productor=user)
        else:
            self.fields["farm"].queryset = Farm.objects.all()

    def validate_farm(self, value):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if (
            user
            and user.is_authenticated
            and not getattr(user, "is_administrator", False)
            and value.id_productor_id != user.id
        ):
            raise serializers.ValidationError("La finca seleccionada no te pertenece.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        farm = attrs.get("farm", getattr(self.instance, "farm", None))
        date = attrs.get("date", getattr(self.instance, "date", None))

        if self.instance is not None and self.instance.is_closed:
            raise serializers.ValidationError(
                {"detail": "No se puede modificar una jornada cerrada."}
            )
        if "date" in attrs and attrs["date"] > timezone.localdate():
            raise serializers.ValidationError(
                {"date": "No se pueden registrar jornadas con fecha futura."}
            )

        if farm and date:
            producer_id = (
                self.instance.producer_id
                if self.instance is not None
                else farm.id_productor_id
            )
            if farm.id_productor_id != producer_id:
                raise serializers.ValidationError(
                    {"farm": "La finca debe pertenecer al productor de la jornada."}
                )
            workdays = Workday.objects.filter(
                producer_id=producer_id,
                farm=farm,
                date=date,
            )
            if self.instance is not None:
                workdays = workdays.exclude(pk=self.instance.pk)
            if workdays.exists():
                raise serializers.ValidationError(
                    {"date": "Ya existe una jornada para esta finca y fecha."}
                )
        return attrs

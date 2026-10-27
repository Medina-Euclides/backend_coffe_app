from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.accounts.permissions import IsOwnerOrAdmin
from apps.farms.models import Lot
from .models import Worker, ActivityType, Workday, WorkdayDetail, HarvestRecord

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
            'identification', 'first_name', 'last_name', 'phone', 'is_active'
        )
        read_only_fields = ('id',)

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
    """
    Serializador para los registros de pesaje de recolección de café.
    Reglas de negocio aplicadas:
      - Sección 5, Regla 1: 'Cada registro de recolección debe estar relacionado con el detalle de una jornada.'
      - Sección 5, Regla 2: 'La cantidad recolectada debe expresarse en kilogramos.'
      - Sección 3, Regla 5: 'Las actividades de recolección deben distinguirse de las demás.'
        (Solo se permite registrar recolección en labores con is_harvest=True).
      - Aislamiento multi-tenant: Un productor solo puede registrar recolección en sus propias jornadas.
    """

    workday_detail = serializers.PrimaryKeyRelatedField(
        queryset=WorkdayDetail.objects.none()
    )

    class Meta:
        model = HarvestRecord
        fields = ('id', 'workday_detail', 'quantity_kg', 'time', 'settlement_status')
        read_only_fields = ('id',)

    def __init__(self, *args, **kwargs):
        """
        Restringe el queryset de workday_detail para que cada productor solo vea sus propios registros.
        """
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            if getattr(user, 'is_administrator', False):
                self.fields['workday_detail'].queryset = WorkdayDetail.objects.select_related(
                    'activity_type', 'workday'
                ).all()
            else:
                self.fields['workday_detail'].queryset = WorkdayDetail.objects.filter(
                    workday__worker__producer=user
                ).select_related('activity_type', 'workday')

    def validate_workday_detail(self, value):
        """
        Valida que el detalle de jornada pertenezca al productor y corresponda a recolección.
        """
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        # 1. Validación de aislamiento multi-tenant
        if user and user.is_authenticated and not getattr(user, 'is_administrator', False):
            if value.workday.worker.producer_id != user.id:
                raise serializers.ValidationError("El detalle de jornada seleccionado no te pertenece.")

        # 2. Validación de regla de negocio: la actividad debe ser de recolección (is_harvest=True)
        if not value.activity_type.is_harvest:
            raise serializers.ValidationError(
                "Solo se pueden registrar pesajes de recolección en detalles cuya actividad sea de tipo recolección."
            )
        return value

    def validate_quantity_kg(self, value):
        """
        Valida que la cantidad en kilogramos sea un valor mayor a cero.
        """
        if value is None or value <= 0:
            raise serializers.ValidationError("La cantidad recolectada debe ser mayor a 0 kg.")
        return value


class WorkdayDetailSerializer(serializers.ModelSerializer):
    """
    Serializador para el detalle de la jornada (relación entre jornada, actividad y lote).
    Reglas de negocio aplicadas:
      - Sección 4, Regla 2: 'El lote es obligatorio para registrar la ejecución de una labor.'
      - Sección 4, Regla 3: 'Cada jornada debe relacionarse con la actividad correspondiente y el lote donde se realizó.'
      - Sección 1, Regla 5: 'La información de fincas diferentes no debe mezclarse.'
      - Sección 1, Regla 6: 'Un lote desactivado conserva historial pero no debe recibir nuevas labores.'
      - Sección 6, Regla 1 y 2: 'Si la modalidad de pago es por kilogramo, la actividad debe ser de recolección.'
    """

    harvest_records = HarvestRecordSerializer(many=True, read_only=True)
    workday = serializers.PrimaryKeyRelatedField(queryset=Workday.objects.none())
    activity_type = serializers.PrimaryKeyRelatedField(queryset=ActivityType.objects.none())
    lot = serializers.PrimaryKeyRelatedField(queryset=Lot.objects.none())

    activity_name = serializers.CharField(source="activity_type.name", read_only=True)
    lot_name = serializers.CharField(source="lot.name", read_only=True)
    farm_name = serializers.CharField(source="lot.id_farm.name", read_only=True)

    class Meta:
        model = WorkdayDetail
        fields = (
            'id', 'activity_type', 'activity_name', 'workday',
            'lot', 'lot_name', 'farm_name', 'harvest_records'
        )
        read_only_fields = ('id',)

    def __init__(self, *args, **kwargs):
        """
        Restringe las opciones seleccionables de jornada, actividad y lote al productor autenticado.
        """
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            if getattr(user, 'is_administrator', False):
                self.fields['workday'].queryset = Workday.objects.select_related('worker').all()
                self.fields['activity_type'].queryset = ActivityType.objects.all()
                self.fields['lot'].queryset = Lot.objects.select_related('id_farm').all()
            else:
                self.fields['workday'].queryset = Workday.objects.filter(
                    worker__producer=user
                ).select_related('worker')
                self.fields['activity_type'].queryset = ActivityType.objects.filter(producer=user)
                self.fields['lot'].queryset = Lot.objects.filter(
                    id_farm__id_productor=user
                ).select_related('id_farm')

    def validate(self, attrs):
        """
        Valida que todos los recursos involucrados pertenezcan al productor,
        que el lote no esté desactivado y que la modalidad concuerde con el tipo de labor.
        """
        attrs = super().validate(attrs)
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        workday = attrs.get('workday') or getattr(self.instance, 'workday', None)
        activity_type = attrs.get('activity_type') or getattr(self.instance, 'activity_type', None)
        lot = attrs.get('lot') or getattr(self.instance, 'lot', None)

        is_admin = getattr(user, 'is_administrator', False)

        # 1. Validación de aislamiento multi-tenant (si no es administrador)
        if user and user.is_authenticated and not is_admin:
            if workday and workday.worker.producer_id != user.id:
                raise serializers.ValidationError({"workday": "La jornada seleccionada no te pertenece."})
            if activity_type and activity_type.producer_id != user.id:
                raise serializers.ValidationError({"activity_type": "El tipo de actividad seleccionado no te pertenece."})
            if lot and lot.id_farm.id_productor_id != user.id:
                raise serializers.ValidationError({"lot": "El lote seleccionado no pertenece a tus fincas."})

        # 2. Validación de lote activo (Sección 1, Regla 6)
        if lot and not lot.is_active:
            raise serializers.ValidationError({"lot": "No se pueden asociar labores a un lote que se encuentra inactivo."})

        # 3. Validación de concordancia entre modalidad de pago y tipo de labor (Sección 6, Reglas 1 y 2)
        # Las labores distintas de recolección se pagan por jornal; la recolección admite jornal o kg.
        if workday and activity_type:
            if workday.payment_mode == Workday.PaymentMode.KILOGRAM and not activity_type.is_harvest:
                raise serializers.ValidationError(
                    {"activity_type": "Las jornadas con modalidad de pago por kilogramo solo admiten actividades de recolección."}
                )

        return attrs


class WorkdaySerializer(serializers.ModelSerializer):
    """
    Serializador para las jornadas laborales diarias de los trabajadores.
    Reglas de negocio aplicadas:
      - Sección 4, Regla 1: 'Cada jornada debe identificar al trabajador y la fecha de ejecución.'
      - Sección 4, Regla 4: 'Cada ejecución de un trabajador en una fecha debe registrarse como jornada independiente.'
      - Sección 2, Regla 4: 'Los trabajadores inactivos deben conservar sus registros históricos pero no recibir nuevas jornadas.'
      - Sección 6: 'Se debe acordar una tarifa válida por jornal o por kilogramo según la modalidad acordada.'
    """

    details = WorkdayDetailSerializer(many=True, read_only=True)
    worker = serializers.PrimaryKeyRelatedField(queryset=Worker.objects.none())
    worker_name = serializers.CharField(source='worker.__str__', read_only=True)

    class Meta:
        model = Workday
        fields = (
            'id', 'worker', 'worker_name', 'date', 'payment_mode',
            'agreed_rate', 'settlement_status', 'created_at', 'details'
        )
        read_only_fields = ('id', 'created_at')

    def __init__(self, *args, **kwargs):
        """
        Restringe el queryset de trabajadores al productor autenticado para evitar fugas entre cuentas.
        """
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            if getattr(user, 'is_administrator', False):
                self.fields['worker'].queryset = Worker.objects.all()
            else:
                self.fields['worker'].queryset = Worker.objects.filter(producer=user)

    def validate_worker(self, value):
        """
        Valida que el trabajador pertenezca al productor autenticado y se encuentre activo.
        """
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        # 1. Validación multi-tenant de propiedad
        if user and user.is_authenticated and not getattr(user, 'is_administrator', False):
            if value.producer_id != user.id:
                raise serializers.ValidationError("El trabajador seleccionado no te pertenece.")

        # 2. Validación de estado activo (Sección 2, Regla 4)
        if not value.is_active:
            raise serializers.ValidationError("No se pueden registrar jornadas para un trabajador inactivo.")

        return value

    def validate_agreed_rate(self, value):
        """
        Valida que la tarifa acordada sea un valor mayor a cero.
        """
        if value is None or value <= 0:
            raise serializers.ValidationError("La tarifa acordada debe ser un valor positivo.")
        return value

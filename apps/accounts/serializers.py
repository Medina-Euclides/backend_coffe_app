from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    """Datos de registro de un nuevo usuario (productor)."""

    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'email', 'phone_number', 'password')
        read_only_fields = ("id",)

    def validate(self, attrs):
        # Antes se aceptaban contraseñas como "123". Ahora se aplican los
        # validadores de Django (longitud, similitud con el correo/nombre,
        # contraseñas comunes, etc.).
        password = attrs.get("password")
        if password:
            # "Usuario virtual" para que el validador de similitud pueda
            # comparar la contraseña contra el email y los nombres.
            virtual_user = User(
                email=attrs.get("email", ""),
                first_name=attrs.get("first_name", ""),
                last_name=attrs.get("last_name", ""),
            )
            try:
                validate_password(password, virtual_user)
            except DjangoValidationError as error:
                # Los errores se devuelven bajo la clave "password" para que el
                # cliente los muestre junto al campo correspondiente.
                raise serializers.ValidationError({"password": error.messages})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        # Usamos el manager personalizado para encriptar la contraseña correctamente
        user = User.objects.create_user(password=password, **validated_data)
        return user


class LoginSerializer(TokenObtainPairSerializer):
    """Login que además devuelve los datos del usuario y su rol.

    simplejwt ya rechaza las cuentas inactivas ("No active account found"),
    por lo que un usuario desactivado no puede obtener tokens.
    """

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        # Enviamos la info del usuario para que el cliente no tenga que hacer
        # un segundo request a /accounts/profile/ al iniciar sesión.
        data["user"] = {
            "id": str(user.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone_number": user.phone_number,
            "role": user.role,
            "full_name": user.full_name,
        }
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Metadatos dentro del JWT: el cliente puede leer el rol sin
        # consultar la base de datos y el backend puede usarlo en auditorías.
        token["email"] = user.email
        token["role"] = user.role
        return token


class ProfileSerializer(serializers.ModelSerializer):
    """Perfil del usuario autenticado (no se puede cambiar el correo ni el rol)."""

    role = serializers.CharField(read_only=True)  # Código del rol: ADMIN / PRODUCER
    role_label = serializers.CharField(source="get_role_display", read_only=True)  # Texto para mostrar
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'email', 'phone_number', 'role', 'role_label', 'full_name')
        read_only_fields = ('id', 'email', 'role', 'role_label', 'full_name')  # El correo no debería cambiar libremente por seguridad


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)

    def validate_new_password(self, value):
        # Validamos la nueva contraseña con las reglas del proyecto.
        validate_password(value, self.context.get("user"))
        return value


class AdminUserSerializer(serializers.ModelSerializer):
    """Gestión del catálogo de usuarios (solo administradores).

    Permite crear usuarios con rol, cambiar su rol, activarlos/desactivarlos
    y establecer contraseñas desde el panel/API.
    """

    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = User
        fields = (
            'id', 'first_name', 'last_name', 'email', 'phone_number',
            'role', 'is_active', 'date_joined', 'password',
        )
        read_only_fields = ('id', 'date_joined')

    def validate(self, attrs):
        password = attrs.get("password")
        # Al crear un usuario desde el panel la contraseña es obligatoria;
        # al editarlo es opcional (si no viene, se conserva la actual).
        if self.instance is None and not password:
            raise serializers.ValidationError(
                {"password": "La contraseña es obligatoria para crear un usuario."}
            )
        if password:
            virtual_user = User(
                email=attrs.get("email", ""),
                first_name=attrs.get("first_name", ""),
                last_name=attrs.get("last_name", ""),
            )
            try:
                validate_password(password, virtual_user)
            except DjangoValidationError as error:
                # Igual que en el registro: el error viaja bajo "password".
                raise serializers.ValidationError({"password": error.messages})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        # create_user() se encarga de encriptar la contraseña.
        return User.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance

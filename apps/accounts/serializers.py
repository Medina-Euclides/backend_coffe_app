from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()

class RegistroSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'email', 'phone_number', 'password')
        read_only_fields = ("id",)

    def create(self, validated_data):
        password = validated_data.pop('password')
        # Usamos el manager personalizado para encriptar la contraseña correctamente
        user = User.objects.create_user(password=password, **validated_data)
        return user


class PerfilSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'email', 'phone_number')
        read_only_fields = ('id', 'email') # El correo no debería cambiar libremente por seguridad


class CambioPasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)


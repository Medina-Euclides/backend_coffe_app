from django.contrib.auth import get_user_model
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from .permissions import IsAdministrator
from .serializers import (
    AdminUserSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    ProfileSerializer,
    RegisterSerializer,
)

User = get_user_model()


class LoginView(TokenObtainPairView):
    """Login con email + contraseña.

    Devuelve access/refresh token y los datos del usuario (incluido su rol).
    Las cuentas inactivas son rechazadas por simplejwt con un 401.
    """

    serializer_class = LoginSerializer
    permission_classes = [AllowAny]


class RegisterView(generics.CreateAPIView):
    """Registro público de un nuevo productor."""

    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer


class ProfileView(generics.RetrieveUpdateAPIView):
    """GET / PATCH del perfil del usuario autenticado (no se admite el ID en la URL)."""

    permission_classes = [IsAuthenticated]
    serializer_class = ProfileSerializer

    def get_object(self):
        # Retorna el usuario autenticado basado en el token JWT enviado desde React
        return self.request.user


class ChangePasswordView(generics.UpdateAPIView):
    """Cambio de contraseña: exige la actual y valida la nueva."""

    permission_classes = [IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    def get_serializer_context(self):
        # Pasamos el usuario al serializer para que los validadores de Django
        # puedan comparar la nueva contraseña con su email/nombre.
        context = super().get_serializer_context()
        context["user"] = self.request.user
        return context

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = self.request.user

        # Validamos que la contraseña antigua sea correcta
        if not user.check_password(serializer.validated_data['old_password']):
            return Response(
                {"old_password": ["La contraseña actual es incorrecta."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        # La nueva contraseña no puede ser la misma que la actual.
        if user.check_password(serializer.validated_data['new_password']):
            return Response(
                {"new_password": ["La nueva contraseña debe ser diferente de la actual."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Asignamos y guardamos la nueva contraseña encriptada
        user.set_password(serializer.validated_data['new_password'])
        user.save()

        return Response({"detail": "Contraseña actualizada exitosamente."}, status=status.HTTP_200_OK)


class UserManagementViewSet(viewsets.ModelViewSet):
    """Módulo de gestión de usuarios (catálogo de productores).

    Solo accesible para administradores. Permite:
      - Listar / consultar usuarios
      - Crear usuarios con un rol concreto
      - Cambiar el rol o los datos de un usuario
      - Activar / desactivar cuentas
    """

    serializer_class = AdminUserSerializer
    queryset = User.objects.all().order_by("email")
    permission_classes = [IsAuthenticated, IsAdministrator]
    # No se permite el borrado físico desde la API: se desactiva la cuenta.
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Desactiva la cuenta (el usuario deja de poder iniciar sesión)."""
        user = self.get_object()
        # Un administrador no puede dejar el sistema sin su propia cuenta.
        if user == request.user:
            return Response(
                {"detail": "No puedes desactivar tu propia cuenta."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(self.get_serializer(user).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Reactiva una cuenta desactivada."""
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=["is_active"])
        return Response(self.get_serializer(user).data, status=status.HTTP_200_OK)

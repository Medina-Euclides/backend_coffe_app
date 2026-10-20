from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from .serializers import (
    RegistroSerializer,
    PerfilSerializer,
    CambioPasswordSerializer
)

class RegistroView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegistroSerializer


class PerfilView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PerfilSerializer

    def get_object(self):
        # Retorna el usuario autenticado basado en el token JWT enviado desde React
        return self.request.user


class CambioPasswordView(generics.UpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CambioPasswordSerializer

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
        
        # Asignamos y guardamos la nueva contraseña encriptada
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        return Response({"detail": "Contraseña actualizada exitosamente."}, status=status.HTTP_200_OK)
    
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import RegistroView, PerfilView, CambioPasswordView

urlpatterns = [
    path('register/', RegistroView.as_view(), name='register'),
    path('login/', TokenObtainPairView.as_view(), name='login'), # Genera el Access y Refresh token
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('profile/', PerfilView.as_view(), name='profile'), # GET (ver perfil) y PUT/PATCH (actualizar datos)
    path('change-password/', CambioPasswordView.as_view(), name='change_password'), # PUT para cambiar contraseña
]

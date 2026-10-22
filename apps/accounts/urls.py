from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from .views import (
    ChangePasswordView,
    LoginView,
    ProfileView,
    RegisterView,
    UserManagementViewSet,
)

# Router del módulo de gestión de usuarios (solo administradores).
router_users = DefaultRouter()
router_users.register(r'users', UserManagementViewSet, basename='user')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),  # Genera el Access y Refresh token
    # Refresco del access token (el refresh rota y el anterior queda revocado
    # gracias a la app token_blacklist instalada en settings).
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('profile/', ProfileView.as_view(), name='profile'),  # GET (ver perfil) y PUT/PATCH (actualizar datos)
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),  # PUT para cambiar contraseña
    # Gestión del catálogo de usuarios (listar, crear, cambiar rol, activar/desactivar)
    path('', include(router_users.urls)),
]

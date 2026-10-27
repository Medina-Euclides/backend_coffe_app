from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole

User = get_user_model()


class AccountsAPITests(APITestCase):
    """
    Pruebas automatizadas del módulo accounts:
      - Registro público de productores.
      - Validación de contraseñas seguras.
      - Autenticación mediante tokens JWT (login, refresh, verify y blacklist).
      - Perfil del usuario autenticado e inmutabilidad de campos críticos.
      - Cambio seguro de contraseña.
      - Permisos administrativos y catálogo de usuarios.
    """

    def setUp(self):
        """Prepara datos iniciales para las pruebas."""
        self.producer = User.objects.create_user(
            email="productor.prueba@cafetera.com",
            password="PasswordSegura123!",
            first_name="Carlos",
            last_name="Restrepo",
            role=UserRole.PRODUCER,
        )
        self.admin_user = User.objects.create_superuser(
            email="admin.prueba@cafetera.com",
            password="AdminPassword123!",
            first_name="Admin",
            last_name="General",
        )

    def test_register_producer_success(self):
        """Verifica el registro exitoso de un productor."""
        payload = {
            "email": "nuevo.productor@cafetera.com",
            "password": "PasswordNuevo123!",
            "first_name": "Mateo",
            "last_name": "Morales",
            "phone_number": "3123456789",
        }
        response = self.client.post("/accounts/register/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["email"], payload["email"])

    def test_register_weak_password_rejected(self):
        """Verifica que una contraseña débil sea rechazada por los validadores de Django."""
        payload = {
            "email": "debil@cafetera.com",
            "password": "123",
            "first_name": "Debil",
            "last_name": "Usuario",
        }
        response = self.client.post("/accounts/register/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_register_duplicate_email_rejected(self):
        """Verifica que no se permita registrar un correo ya existente."""
        payload = {
            "email": "productor.prueba@cafetera.com",
            "password": "PasswordOtra123!",
            "first_name": "Otro",
            "last_name": "Nombre",
        }
        response = self.client.post("/accounts/register/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_login_success_and_jwt_tokens(self):
        """Verifica inicio de sesión exitoso y generación de access/refresh tokens con rol."""
        payload = {
            "email": "productor.prueba@cafetera.com",
            "password": "PasswordSegura123!",
        }
        response = self.client.post("/accounts/login/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["role"], UserRole.PRODUCER)

    def test_login_invalid_password(self):
        """Verifica rechazo con credenciales erróneas."""
        payload = {
            "email": "productor.prueba@cafetera.com",
            "password": "PasswordIncorrecta!",
        }
        response = self.client.post("/accounts/login/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_token_rotation_and_blacklist(self):
        """Verifica rotación de refresh token y revocación del anterior."""
        login_res = self.client.post(
            "/accounts/login/",
            {"email": "productor.prueba@cafetera.com", "password": "PasswordSegura123!"},
            format="json",
        )
        refresh_token = login_res.data["refresh"]

        # Rotar token
        refresh_res = self.client.post("/accounts/token/refresh/", {"refresh": refresh_token}, format="json")
        self.assertEqual(refresh_res.status_code, status.HTTP_200_OK)
        self.assertIn("access", refresh_res.data)

        # Reusar el anterior (debe fallar por estar en blacklist)
        reuse_res = self.client.post("/accounts/token/refresh/", {"refresh": refresh_token}, format="json")
        self.assertEqual(reuse_res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_profile_read_and_update(self):
        """Verifica consulta y actualización del perfil, asegurando inmutabilidad de rol y correo."""
        self.client.force_authenticate(user=self.producer)

        # Consultar perfil
        get_res = self.client.get("/accounts/profile/")
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)
        self.assertEqual(get_res.data["email"], self.producer.email)

        # Actualizar datos permitidos e intentar modificar rol/correo protegidos
        patch_res = self.client.patch(
            "/accounts/profile/",
            {"phone_number": "3009998877", "role": "ADMIN", "email": "hacked@cafetera.com"},
            format="json",
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data["phone_number"], "3009998877")
        self.assertEqual(patch_res.data["role"], UserRole.PRODUCER)
        self.assertEqual(patch_res.data["email"], self.producer.email)

    def test_change_password(self):
        """Verifica cambio de contraseña requiriendo la actual."""
        self.client.force_authenticate(user=self.producer)
        payload = {
            "old_password": "PasswordSegura123!",
            "new_password": "NuevaPasswordSegura456!",
        }
        res = self.client.put("/accounts/change-password/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Verificar que la nueva contraseña funciona en login
        self.client.force_authenticate(user=None)
        login_res = self.client.post(
            "/accounts/login/",
            {"email": "productor.prueba@cafetera.com", "password": "NuevaPasswordSegura456!"},
            format="json",
        )
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)

    def test_admin_permissions_on_user_management(self):
        """Verifica que solo administradores pueden gestionar el catálogo de usuarios."""
        # Productor normal es rechazado con 403 Forbidden
        self.client.force_authenticate(user=self.producer)
        res_prod = self.client.get("/accounts/users/")
        self.assertEqual(res_prod.status_code, status.HTTP_403_FORBIDDEN)

        # Administrador tiene acceso
        self.client.force_authenticate(user=self.admin_user)
        res_admin = self.client.get("/accounts/users/")
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)

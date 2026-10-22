import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


# Create your models here.
class UserRole(models.TextChoices):
    """Roles que controlan qué puede ver y hacer cada usuario.

    Por ahora solo existen dos roles:
      - ADMIN: administra el sistema (ve todas las fincas y gestiona usuarios).
      - PRODUCER: dueño de la finca, solo ve sus propias fincas y lotes.

    NOTA: un rol de "trabajador" (con lotes asignados) quedó como mejora futura.
    """

    ADMIN = "ADMIN", "Administrador"
    PRODUCER = "PRODUCER", "Productor"


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('El correo electrónico es obligatorio')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        # Un superusuario siempre es administrador del sistema.
        extra_fields.setdefault('role', UserRole.ADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(unique=True, max_length=200)
    first_name = models.CharField(max_length=150, blank=False, null=False)
    last_name = models.CharField(max_length=150, blank=False, null=False)
    phone_number = models.CharField(max_length=20, blank=True)

    # Rol del usuario: define qué fincas/lotes puede ver y si puede administrar
    # el catálogo de usuarios. Por defecto es productor (dueño de sus fincas).
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.PRODUCER,
        db_index=True,
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        verbose_name = "productor"
        verbose_name_plural = "productores"

    def __str__(self):
        return f"{self.first_name} {self.last_name} {self.email}"

    @property
    def full_name(self) -> str:
        """Nombre legible para mostrar en el cliente (fincas, lotes, listados)."""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_administrator(self) -> bool:
        """Verdadero si el usuario administra todo el sistema (ve todas las fincas)."""
        return self.is_superuser or self.role == UserRole.ADMIN

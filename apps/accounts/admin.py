from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

# Register your models here.
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    # Columnas que se verán en la tabla general del panel de administración
    list_display = ("email", "first_name", "last_name", "phone_number", "is_staff", "is_superuser")
    
    # Filtros laterales para separar rápidamente administradores de productores
    list_filter = ("is_staff", "is_superuser", "is_active")
    
    # Campos por los que se podrá buscar en la barra superior
    search_fields = ("email", "first_name", "last_name")
    
    ordering = ('email',)

    # Como eliminamos el 'username', debemos ajustar los campos de edición en el panel 
    # para que no busquen el campo username al crear o editar un usuario desde el admin.
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Información Personal', {'fields': ('first_name', 'last_name', 'phone_number')}),
        ('Permisos y Accesos', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Fechas importantes', {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'phone_number', 'password1', 'password2', 'is_staff', 'is_active')}
        ),
    )
    
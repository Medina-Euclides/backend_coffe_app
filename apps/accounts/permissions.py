from rest_framework.permissions import BasePermission


class IsAdministrator(BasePermission):
    """Permiso para el módulo de gestión de usuarios.

    Solo los usuarios con rol ADMIN (o superusuarios) pueden entrar.
    """

    message = "Necesitas permisos de administrador para realizar esta acción."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_administrator)

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsOwnerOrAdmin(BasePermission):
    """Permiso a nivel de objeto para fincas y lotes.

    Reglas:
      - Administrador: acceso total.
      - Productor: sus propias fincas y los lotes de esas fincas.

    Nota: los listados ya vienen filtrados en las vistas (get_queryset), este
    permiso protege las operaciones sobre un objeto concreto (PATCH/DELETE).
    """

    message = "No tienes permisos sobre este recurso."

    def has_permission(self, request, view):
        # Cualquier usuario autenticado puede operar; el filtro real de qué
        # objetos ve se hace en el get_queryset de cada vista.
        user = request.user
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        # El administrador tiene permisos sobre cualquier objeto.
        if user.is_administrator:
            return True

        # Objeto tipo Farm: el dueño es el campo id_productor.
        owner_id = getattr(obj, "id_productor_id", None)
        if owner_id is not None:
            return owner_id == user.id

        # Objeto tipo Lot: el dueño es el dueño de la finca.
        if getattr(obj, "id_farm_id", None) is not None:
            return obj.id_farm.id_productor_id == user.id

        return False

from rest_framework.permissions import BasePermission


class IsAdministrator(BasePermission):
    """Permiso para administradores del sistema (rol ADMIN o superusuarios)."""

    message = "Necesitas permisos de administrador para realizar esta acción."

    def has_permission(self, request, view):
        """Verifica que el usuario esté autenticado y sea administrador."""
        user = request.user
        return bool(user and user.is_authenticated and user.is_administrator)

    def has_object_permission(self, request, view, obj):
        """Valida permisos a nivel de objeto para administradores."""
        return self.has_permission(request, view)


class IsOwnerOrAdmin(BasePermission):
    """Permiso a nivel de objeto: administradores tienen acceso total y productores solo a sus recursos."""

    message = "No tienes permisos sobre este recurso."

    def has_permission(self, request, view):
        """Permite operar a cualquier usuario autenticado; el filtrado se realiza por consulta."""
        user = request.user
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        """Valida que el usuario sea administrador o el dueño directo/indirecto del recurso."""
        user = request.user
        if not (user and user.is_authenticated):
            return False

        if user.is_administrator:
            return True

        # 1. Campo de dueño directo (id_productor o producer)
        owner_id = getattr(obj, "id_productor_id", None) or getattr(obj, "producer_id", None)
        if owner_id is not None:
            return owner_id == user.id

        # 2. Relación a finca (id_farm o farm)
        farm = getattr(obj, "id_farm", None) or getattr(obj, "farm", None)
        if farm is not None:
            farm_owner = getattr(farm, "id_productor_id", None) or getattr(farm, "producer_id", None)
            return farm_owner == user.id

        # 3. Relación a trabajador (worker)
        worker = getattr(obj, "worker", None)
        if worker is not None:
            return getattr(worker, "producer_id", None) == user.id

        # 4. Relación a jornada laboral (workday)
        workday = getattr(obj, "workday", None)
        if workday is not None and getattr(workday, "worker", None) is not None:
            return getattr(workday.worker, "producer_id", None) == user.id

        # 5. Relación a liquidación (settlement): detalles de liquidación y pagos
        settlement = getattr(obj, "settlement", None)
        if settlement is not None and getattr(settlement, "worker", None) is not None:
            return getattr(settlement.worker, "producer_id", None) == user.id

        # 6. Relación a detalle de jornada (workday_detail): registros de recolección
        workday_detail = getattr(obj, "workday_detail", None)
        if workday_detail is not None:
            related_workday = getattr(workday_detail, "workday", None)
            if related_workday is not None and getattr(related_workday, "worker", None) is not None:
                return getattr(related_workday.worker, "producer_id", None) == user.id

        return False


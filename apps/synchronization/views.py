from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import apply_operation, build_snapshot

MAX_OPERATIONS_PER_REQUEST = 200


class SyncPushView(APIView):
    """
    Recibe la cola de operaciones registradas sin conexión y las aplica en orden.

    Cuerpo: {"operations": [{"op_id", "entity", "action", "object_id", "data", "client_ts"}]}
    Respuesta: {"results": [{"op_id", "status": applied|duplicate|rejected, ...}], "server_time"}

    Cada operación se aplica en su propia transacción: si una se rechaza, las demás continúan.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        operations = request.data.get("operations")
        if not isinstance(operations, list):
            return Response(
                {"operations": "Debe ser una lista de operaciones."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(operations) > MAX_OPERATIONS_PER_REQUEST:
            return Response(
                {"operations": f"Máximo {MAX_OPERATIONS_PER_REQUEST} operaciones por envío."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        results = [apply_operation(request, op if isinstance(op, dict) else {}) for op in operations]
        return Response({"results": results, "server_time": timezone.now()})


class SyncPullView(APIView):
    """Descarga los datos operativos del usuario para trabajar sin conexión."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"data": build_snapshot(request), "server_time": timezone.now()})


class SyncPingView(APIView):
    """Respuesta mínima para que el dispositivo compruebe si el servidor está disponible."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"ok": True, "server_time": timezone.now()})

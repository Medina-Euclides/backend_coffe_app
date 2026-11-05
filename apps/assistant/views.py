import logging

from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    AssistantConfigurationError,
    AssistantProviderError,
    AssistantService,
)


logger = logging.getLogger(__name__)


class AssistantQuestionSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000, trim_whitespace=True)
    history = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
        max_length=8,
    )

    def validate_history(self, history):
        validated_history = []
        for message in history:
            if set(message) != {"role", "content"}:
                raise serializers.ValidationError(
                    "Cada mensaje del historial debe tener role y content."
                )
            role = message["role"]
            content = message["content"]
            if role not in ("user", "assistant"):
                raise serializers.ValidationError(
                    "El historial solo puede incluir mensajes user y assistant."
                )
            if not isinstance(content, str) or not content.strip():
                raise serializers.ValidationError(
                    "El contenido de cada mensaje debe ser texto no vacío."
                )
            if len(content) > 2000:
                raise serializers.ValidationError(
                    "Cada mensaje del historial debe tener máximo 2000 caracteres."
                )
            validated_history.append(
                {"role": role, "content": content.strip()}
            )
        return validated_history


class AssistantAskView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        question_serializer = AssistantQuestionSerializer(data=request.data)
        question_serializer.is_valid(raise_exception=True)

        try:
            answer = AssistantService.ask(
                user=request.user,
                question=question_serializer.validated_data["question"],
                history=question_serializer.validated_data["history"],
            )
        except AssistantConfigurationError:
            logger.error("Assistant provider is not configured.")
            return Response(
                {"detail": "El asistente de IA no está configurado."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except AssistantProviderError:
            logger.error("Assistant provider request failed.")
            return Response(
                {"detail": "No se pudo obtener una respuesta del asistente."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({"answer": answer}, status=status.HTTP_200_OK)

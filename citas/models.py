from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from agenda.models import Cupo
from pacientes.models import Paciente


def dias_aviso_defecto() -> int:
    return settings.CITA_DIAS_AVISO_DEFECTO


class Cita(models.Model):
    class Estado(models.TextChoices):
        AGENDADA = "agendada", "Agendada"
        CONFIRMADA = "confirmada", "Confirmada"
        CANCELADA = "cancelada", "Cancelada"
        SIN_RESPUESTA = "sin_respuesta", "Sin respuesta"

    # Estados que ocupan el cupo (todo lo que no está cancelado).
    VIGENTES = (Estado.AGENDADA, Estado.CONFIRMADA, Estado.SIN_RESPUESTA)

    cupo = models.ForeignKey(Cupo, on_delete=models.PROTECT, related_name="citas")
    paciente = models.ForeignKey(Paciente, on_delete=models.PROTECT, related_name="citas")
    estado = models.CharField(max_length=15, choices=Estado.choices, default=Estado.AGENDADA)
    dias_aviso = models.PositiveSmallIntegerField("días de aviso", default=dias_aviso_defecto)  # Cita.diasAviso
    es_sobrecupo = models.BooleanField("es sobrecupo", default=False)  # Cita.esSobrecupo
    cita_original = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="sobrecupos",
        help_text="Para un sobrecupo: la cita 'sin respuesta' que lo originó (RN-07).",
    )
    # RN-01: tratamientos de varias sesiones agendadas de una vez
    grupo_sesiones = models.UUIDField(null=True, blank=True, db_index=True)
    numero_sesion = models.PositiveSmallIntegerField(default=1)
    total_sesiones = models.PositiveSmallIntegerField(default=1)
    observaciones = models.CharField(max_length=300, blank=True)

    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="citas_creadas")
    creada_en = models.DateTimeField(default=timezone.now)
    recordatorio_enviado_en = models.DateTimeField(null=True, blank=True)
    respuesta_en = models.DateTimeField(null=True, blank=True)
    cancelada_en = models.DateTimeField(null=True, blank=True)
    cancelada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    motivo_cancelacion = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["cupo__fecha", "cupo__hora_inicio", "es_sobrecupo"]
        constraints = [
            # RN-02: un cupo no puede tener dos citas normales vigentes.
            models.UniqueConstraint(
                fields=["cupo"], condition=Q(es_sobrecupo=False, estado__in=["agendada", "confirmada", "sin_respuesta"]),
                name="una_cita_normal_vigente_por_cupo",
            ),
            # RN-07: como máximo un sobrecupo vigente por cupo (=> máximo 2 citas por cupo).
            models.UniqueConstraint(
                fields=["cupo"], condition=Q(es_sobrecupo=True, estado__in=["agendada", "confirmada", "sin_respuesta"]),
                name="un_sobrecupo_vigente_por_cupo",
            ),
        ]

    def __str__(self):
        tipo = " (sobrecupo)" if self.es_sobrecupo else ""
        return f"{self.paciente.nombre} · {self.cupo}{tipo}"

    @property
    def es_vigente(self) -> bool:
        return self.estado in self.VIGENTES

    @property
    def fecha_aviso(self):
        """Fecha en que corresponde enviar el recordatorio (fecha de la cita - diasAviso)."""
        return self.cupo.fecha - timedelta(days=self.dias_aviso)

    @property
    def es_pasada(self) -> bool:
        return self.cupo.fecha < timezone.localdate()


class MensajeEnviado(models.Model):
    """Registro de mensajes de NotificadorLog (simula el envío por WhatsApp)."""

    class Tipo(models.TextChoices):
        AGENDAMIENTO = "agendamiento", "Cita agendada"
        RECORDATORIO = "recordatorio", "Recordatorio / solicitud de confirmación"
        CONFIRMACION = "confirmacion", "Confirmación recibida"
        CANCELACION = "cancelacion", "Cancelación"
        OTRO = "otro", "Otro"

    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="mensajes")
    cita = models.ForeignKey(Cita, null=True, blank=True, on_delete=models.SET_NULL, related_name="mensajes")
    destinatario = models.CharField(max_length=150, help_text="Nombre y celular de quien recibe el mensaje.")
    canal = models.CharField(max_length=40, default="WhatsApp (simulado)")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    mensaje = models.TextField()
    enviado_en = models.DateTimeField(default=timezone.now)
    enviado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-enviado_en", "-id"]
        verbose_name = "mensaje enviado"
        verbose_name_plural = "mensajes enviados"

    def __str__(self):
        return f"{self.get_tipo_display()} → {self.destinatario}"

from django.conf import settings
from django.db import models
from django.utils import timezone

from pacientes.models import Paciente
from profesionales.models import Especialidad, Policlinico, Profesional


class SolicitudEspera(models.Model):
    """RN-06: lista de espera por orden de llegada (las TENS pueden subir a un paciente)."""

    class Estado(models.TextChoices):
        EN_ESPERA = "en_espera", "En espera"
        CONTACTADO = "contactado", "Contactado"
        SIN_CONTACTO = "sin_contacto", "Sin contacto"
        AGENDADO = "agendado", "Agendado"
        RETIRADO = "retirado", "Retirado"

    class Resultado(models.TextChoices):
        SIN_RESULTADO = "sin_resultado", "Sin resultado"
        NO_CONTESTA = "no_contesta", "No contesta"
        NUMERO_ERRONEO = "numero_erroneo", "Número equivocado"
        ACEPTA = "acepta", "Acepta una hora"
        RECHAZA = "rechaza", "Rechaza la hora ofrecida"
        YA_NO_NECESITA = "ya_no_necesita", "Ya no necesita atención"

    ACTIVOS = (Estado.EN_ESPERA, Estado.CONTACTADO, Estado.SIN_CONTACTO)

    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="solicitudes_espera")
    especialidad = models.ForeignKey(Especialidad, on_delete=models.PROTECT, related_name="solicitudes_espera")
    profesional = models.ForeignKey(Profesional, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="solicitudes_espera", help_text="Vacío = cualquier profesional.")
    policlinico = models.ForeignKey(Policlinico, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    estado = models.CharField(max_length=15, choices=Estado.choices, default=Estado.EN_ESPERA)
    resultado_contacto = models.CharField("resultado del contacto", max_length=20, choices=Resultado.choices,
                                          default=Resultado.SIN_RESULTADO)
    nota = models.TextField(blank=True)
    orden = models.PositiveIntegerField(default=0, db_index=True, help_text="Posición (orden de llegada).")
    canal = models.CharField(max_length=12, default="presencial")
    creada_en = models.DateTimeField(default=timezone.now)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actualizada_en = models.DateTimeField(auto_now=True)
    cita = models.ForeignKey("citas.Cita", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["orden", "creada_en"]
        verbose_name = "solicitud de lista de espera"
        verbose_name_plural = "lista de espera"

    def __str__(self):
        return f"{self.paciente.nombre} · {self.especialidad}"

    @property
    def activa(self) -> bool:
        return self.estado in self.ACTIVOS

    @property
    def dias_en_espera(self) -> int:
        return (timezone.localdate() - timezone.localtime(self.creada_en).date()).days

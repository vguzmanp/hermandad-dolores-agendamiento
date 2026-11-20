from django.conf import settings
from django.db import models
from django.utils import timezone

from citas.models import Cita


class Asistencia(models.Model):
    """Registro de si el paciente asistió (o no) a su cita."""

    cita = models.OneToOneField(Cita, on_delete=models.CASCADE, related_name="asistencia")
    asistio = models.BooleanField()
    registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    registrada_en = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "asistencia"

    def __str__(self):
        return f"{self.cita.paciente.nombre}: {'asistió' if self.asistio else 'no asistió'}"

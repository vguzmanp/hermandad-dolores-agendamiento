from django.conf import settings
from django.db import models


class Policlinico(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    direccion = models.CharField("dirección", max_length=200, blank=True)
    es_telemedicina = models.BooleanField("es telemedicina", default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["es_telemedicina", "nombre"]
        verbose_name = "policlínico"
        verbose_name_plural = "policlínicos"

    def __str__(self):
        return self.nombre


class Especialidad(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    duracion_cupo_min = models.PositiveSmallIntegerField("duración del cupo (min)", default=30)
    # RN-01: según la especialidad se pueden agendar todas las sesiones de una vez
    permite_agendar_todas_sesiones = models.BooleanField("permite agendar todas las sesiones de una vez", default=False)
    sesiones_por_tratamiento = models.PositiveSmallIntegerField("sesiones por tratamiento", default=1)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "especialidad"
        verbose_name_plural = "especialidades"

    def __str__(self):
        return self.nombre


class Profesional(models.Model):
    """Especialidad 1 — 0..* Profesional. Se relaciona con Policlínico mediante Agenda."""

    nombre = models.CharField("nombre completo", max_length=150)
    rut = models.CharField("RUT", max_length=12, unique=True)
    especialidad = models.ForeignKey(Especialidad, on_delete=models.PROTECT, related_name="profesionales")
    celular = models.CharField(max_length=20, blank=True)
    correo = models.EmailField("correo electrónico", blank=True)
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="profesional", help_text="Usuario del sistema (rol Profesional), si tiene.",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "profesional"
        verbose_name_plural = "profesionales"

    def __str__(self):
        return f"{self.nombre} — {self.especialidad}"

    @property
    def policlinicos(self):
        """Policlínicos donde atiende (a través de sus agendas)."""
        return Policlinico.objects.filter(agendas__profesional=self, agendas__activa=True).distinct()

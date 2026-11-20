from django.conf import settings
from django.db import models


class Policlinico(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    direccion = models.CharField("dirección", max_length=200, blank=True)
    es_telemedicina = models.BooleanField("es telemedicina", default=False)
    usuario_tens = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="policlinico_tens",
        verbose_name="usuario TENS/TONS",
        help_text="Cuenta con la que las TENS/TONS de este policlínico entran al sistema (se llama como el policlínico).",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["es_telemedicina", "nombre"]
        verbose_name = "policlínico"
        verbose_name_plural = "policlínicos"

    def __str__(self):
        return self.nombre

    @property
    def especialidades(self):
        """Especialidades que se atienden en el policlínico (según los horarios activos)."""
        return Especialidad.objects.filter(
            profesionales__agendas__policlinico=self, profesionales__agendas__activa=True,
            profesionales__activo=True, activa=True).distinct()


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

    @property
    def policlinicos(self):
        """Policlínicos donde se atiende la especialidad (según los horarios activos)."""
        return Policlinico.objects.filter(
            agendas__profesional__especialidad=self, agendas__activa=True,
            agendas__profesional__activo=True, activo=True).distinct()


class Profesional(models.Model):
    """
    Especialidad 1 — 0..* Profesional. Se relaciona con Policlínico mediante Agenda.
    Los profesionales no usan el sistema: la Administración gestiona sus horarios.
    """

    nombre = models.CharField("nombre completo", max_length=150)
    rut = models.CharField("RUT", max_length=12, unique=True)
    especialidad = models.ForeignKey(Especialidad, on_delete=models.PROTECT, related_name="profesionales")
    celular = models.CharField(max_length=20, blank=True)
    correo = models.EmailField("correo electrónico", blank=True)
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

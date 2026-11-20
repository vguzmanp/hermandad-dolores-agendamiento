from django.db import models

from profesionales.models import Policlinico, Profesional


class Agenda(models.Model):
    """
    Bloque semanal de atención: relaciona Profesional y Policlínico.
    Ej.: Dra. X atiende los lunes de 09:00 a 13:00 en el Policlínico Y, cupos de 30 min.
    """

    class DiaSemana(models.IntegerChoices):
        LUNES = 0, "Lunes"
        MARTES = 1, "Martes"
        MIERCOLES = 2, "Miércoles"
        JUEVES = 3, "Jueves"
        VIERNES = 4, "Viernes"
        SABADO = 5, "Sábado"
        DOMINGO = 6, "Domingo"

    profesional = models.ForeignKey(Profesional, on_delete=models.PROTECT, related_name="agendas")
    policlinico = models.ForeignKey(Policlinico, on_delete=models.PROTECT, related_name="agendas", verbose_name="policlínico")
    dia_semana = models.PositiveSmallIntegerField("día de la semana", choices=DiaSemana.choices)
    hora_inicio = models.TimeField("hora de inicio")
    hora_fin = models.TimeField("hora de término")
    duracion_cupo_min = models.PositiveSmallIntegerField(
        "duración de cada cupo (min)", null=True, blank=True,
        help_text="Si se deja vacío se usa la duración definida en la especialidad.",
    )
    vigente_desde = models.DateField("vigente desde")
    vigente_hasta = models.DateField("vigente hasta", null=True, blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["profesional__nombre", "dia_semana", "hora_inicio"]
        verbose_name = "agenda"

    def __str__(self):
        return (f"{self.profesional.nombre} · {self.policlinico} · {self.get_dia_semana_display()} "
                f"{self.hora_inicio:%H:%M}-{self.hora_fin:%H:%M}")

    @property
    def duracion_efectiva(self) -> int:
        return self.duracion_cupo_min or self.profesional.especialidad.duracion_cupo_min

    @property
    def minutos(self) -> int:
        return (self.hora_fin.hour * 60 + self.hora_fin.minute) - (self.hora_inicio.hour * 60 + self.hora_inicio.minute)

    @property
    def cupos_por_bloque(self) -> int:
        return self.minutos // self.duracion_efectiva


class Cupo(models.Model):
    """Espacio concreto de atención (fecha + hora) generado desde una Agenda."""

    class Estado:
        LIBRE = "libre"
        OCUPADO = "ocupado"
        SOBRECUPO_DISPONIBLE = "sobrecupo_disponible"  # la cita normal está sin_respuesta (RN-07)
        CON_SOBRECUPO = "con_sobrecupo"
        BLOQUEADO = "bloqueado"

    ETIQUETAS = {
        Estado.LIBRE: "Libre",
        Estado.OCUPADO: "Ocupado",
        Estado.SOBRECUPO_DISPONIBLE: "Sin respuesta · admite sobrecupo",
        Estado.CON_SOBRECUPO: "Ocupado + sobrecupo",
        Estado.BLOQUEADO: "Bloqueado",
    }

    agenda = models.ForeignKey(Agenda, on_delete=models.CASCADE, related_name="cupos")
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    bloqueado = models.BooleanField(default=False)
    motivo_bloqueo = models.CharField("motivo del bloqueo", max_length=200, blank=True)

    class Meta:
        ordering = ["fecha", "hora_inicio"]
        constraints = [
            models.UniqueConstraint(fields=["agenda", "fecha", "hora_inicio"], name="cupo_unico_por_agenda_fecha_hora"),
        ]

    def __str__(self):
        return f"{self.fecha:%d/%m/%Y} {self.hora_inicio:%H:%M} · {self.agenda.profesional.nombre} · {self.agenda.policlinico}"

    @property
    def profesional(self):
        return self.agenda.profesional

    @property
    def policlinico(self):
        return self.agenda.policlinico

    @property
    def citas_vigentes(self) -> list:
        """Citas no canceladas del cupo (usa prefetch_related('citas') si está disponible)."""
        relacion = getattr(self, "citas", None)
        if relacion is None:
            return []
        return [c for c in relacion.all() if c.estado != "cancelada"]

    @property
    def cita_normal(self):
        return next((c for c in self.citas_vigentes if not c.es_sobrecupo), None)

    @property
    def sobrecupo(self):
        return next((c for c in self.citas_vigentes if c.es_sobrecupo), None)

    @property
    def estado(self) -> str:
        if self.bloqueado:
            return self.Estado.BLOQUEADO
        normal, sobre = self.cita_normal, self.sobrecupo
        if normal is None and sobre is None:
            return self.Estado.LIBRE
        if sobre is not None:
            return self.Estado.CON_SOBRECUPO
        if normal.estado == "sin_respuesta":
            return self.Estado.SOBRECUPO_DISPONIBLE
        return self.Estado.OCUPADO

    @property
    def estado_display(self) -> str:
        return self.ETIQUETAS[self.estado]

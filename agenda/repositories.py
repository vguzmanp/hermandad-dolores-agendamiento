from datetime import date

from django.db.models import Q, QuerySet

from .models import Agenda, Cupo


class AgendaRepository:
    def listar(self, profesional_id=None, policlinico_id=None) -> QuerySet[Agenda]:
        qs = Agenda.objects.select_related("profesional__especialidad", "policlinico")
        if profesional_id:
            qs = qs.filter(profesional_id=profesional_id)
        if policlinico_id:
            qs = qs.filter(policlinico_id=policlinico_id)
        return qs

    def obtener(self, agenda_id: int) -> Agenda:
        return self.listar().get(pk=agenda_id)

    def solapadas(self, agenda: Agenda) -> QuerySet[Agenda]:
        """Agendas activas del mismo profesional, mismo día, con horario y vigencia que se cruzan."""
        qs = Agenda.objects.filter(
            profesional=agenda.profesional, dia_semana=agenda.dia_semana, activa=True,
            hora_inicio__lt=agenda.hora_fin, hora_fin__gt=agenda.hora_inicio,
        ).filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=agenda.vigente_desde))
        if agenda.vigente_hasta:
            qs = qs.filter(vigente_desde__lte=agenda.vigente_hasta)
        if agenda.pk:
            qs = qs.exclude(pk=agenda.pk)
        return qs

    def guardar(self, agenda: Agenda) -> Agenda:
        agenda.save()
        return agenda


class CupoRepository:
    def base(self) -> QuerySet[Cupo]:
        qs = Cupo.objects.select_related("agenda__profesional__especialidad", "agenda__policlinico")
        if hasattr(Cupo, "citas"):  # relación inversa definida por el módulo de citas
            qs = qs.prefetch_related("citas__paciente")
        return qs

    def obtener(self, cupo_id: int) -> Cupo:
        return self.base().get(pk=cupo_id)

    def de_agenda(self, agenda: Agenda, desde: date | None = None, hasta: date | None = None) -> QuerySet[Cupo]:
        qs = self.base().filter(agenda=agenda)
        if desde:
            qs = qs.filter(fecha__gte=desde)
        if hasta:
            qs = qs.filter(fecha__lte=hasta)
        return qs

    def crear_si_no_existe(self, agenda: Agenda, fecha: date, hora_inicio, hora_fin) -> bool:
        _, creado = Cupo.objects.get_or_create(
            agenda=agenda, fecha=fecha, hora_inicio=hora_inicio, defaults={"hora_fin": hora_fin}
        )
        return creado

    def guardar(self, cupo: Cupo) -> Cupo:
        cupo.save()
        return cupo

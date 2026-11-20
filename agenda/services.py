"""Lógica de agendas (bloques semanales) y cupos: generar, bloquear y liberar."""
from datetime import date, datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core import roles
from core.exceptions import ReglaNegocioError

from .models import Agenda, Cupo
from .repositories import AgendaRepository, CupoRepository


class AgendaService:
    def __init__(self, agendas: AgendaRepository | None = None, cupos: CupoRepository | None = None):
        self.agendas = agendas or AgendaRepository()
        self.cupos = cupos or CupoRepository()

    # ------------------------------------------------------------ agendas
    @transaction.atomic
    def guardar_agenda(self, agenda: Agenda, usuario) -> Agenda:
        roles.exigir_rol(usuario, roles.ADMINISTRACION)
        if agenda.hora_fin <= agenda.hora_inicio:
            raise ReglaNegocioError("La hora de término debe ser posterior a la hora de inicio.", "AGENDA")
        if agenda.vigente_hasta and agenda.vigente_hasta < agenda.vigente_desde:
            raise ReglaNegocioError("La vigencia final no puede ser anterior a la inicial.", "AGENDA")
        if agenda.activa:
            choque = self.agendas.solapadas(agenda).first()
            if choque:
                raise ReglaNegocioError(f"El profesional ya tiene un bloque que se cruza: {choque}.", "AGENDA")
        return self.agendas.guardar(agenda)

    # -------------------------------------------------------------- cupos
    @staticmethod
    def horarios_del_bloque(agenda: Agenda):
        """Divide el bloque [hora_inicio, hora_fin) en cupos de la duración configurada."""
        paso = timedelta(minutes=agenda.duracion_efectiva)
        base = date(2000, 1, 1)
        actual = datetime.combine(base, agenda.hora_inicio)
        fin = datetime.combine(base, agenda.hora_fin)
        while actual + paso <= fin:
            yield actual.time(), (actual + paso).time()
            actual += paso

    @transaction.atomic
    def generar_cupos(self, agenda: Agenda, desde: date | None, hasta: date | None, usuario) -> int:
        """Genera los cupos del bloque semanal entre dos fechas. No duplica cupos existentes."""
        roles.exigir_rol(usuario, roles.ADMINISTRACION)
        if not agenda.activa:
            raise ReglaNegocioError("La agenda está inactiva; actívela antes de generar cupos.", "AGENDA")
        hoy = timezone.localdate()
        desde = max(desde or hoy, agenda.vigente_desde, hoy)
        hasta = hasta or (desde + timedelta(weeks=settings.AGENDA_SEMANAS_GENERACION))
        if agenda.vigente_hasta:
            hasta = min(hasta, agenda.vigente_hasta)
        if hasta < desde:
            return 0
        horarios = list(self.horarios_del_bloque(agenda))
        creados = 0
        dia = desde + timedelta(days=(agenda.dia_semana - desde.weekday()) % 7)
        while dia <= hasta:
            for inicio, fin in horarios:
                creados += self.cupos.crear_si_no_existe(agenda, dia, inicio, fin)
            dia += timedelta(weeks=1)
        return creados

    @transaction.atomic
    def bloquear_cupo(self, cupo: Cupo, motivo: str, usuario) -> Cupo:
        roles.exigir_rol(usuario, roles.ADMINISTRACION, roles.TENS)
        # Se bloquea la fila para que no se agende una cita mientras se bloquea el cupo.
        cupo = Cupo.objects.select_related("agenda").select_for_update(of=("self",)).get(pk=cupo.pk)
        roles.exigir_policlinico(usuario, cupo.agenda.policlinico_id)
        if cupo.citas_vigentes:
            raise ReglaNegocioError(
                "El cupo tiene citas vigentes; deben cancelarse antes de bloquearlo.", "AGENDA"
            )
        cupo.bloqueado = True
        cupo.motivo_bloqueo = motivo or "Hora bloqueada"
        return self.cupos.guardar(cupo)

    def liberar_cupo(self, cupo: Cupo, usuario) -> Cupo:
        roles.exigir_rol(usuario, roles.ADMINISTRACION, roles.TENS)
        roles.exigir_policlinico(usuario, cupo.agenda.policlinico_id)
        cupo.bloqueado = False
        cupo.motivo_bloqueo = ""
        return self.cupos.guardar(cupo)

    @transaction.atomic
    def bloquear_dia(self, agenda: Agenda, fecha: date, motivo: str, usuario) -> tuple[int, int]:
        """Bloquea todos los cupos libres de la agenda en una fecha. Devuelve (bloqueados, omitidos)."""
        roles.exigir_rol(usuario, roles.ADMINISTRACION)
        bloqueados = omitidos = 0
        for cupo in self.cupos.de_agenda(agenda, fecha, fecha).select_for_update(of=("self",)):
            if cupo.bloqueado:
                continue
            if cupo.citas_vigentes:
                omitidos += 1
                continue
            cupo.bloqueado, cupo.motivo_bloqueo = True, motivo or "Bloqueo de día completo"
            self.cupos.guardar(cupo)
            bloqueados += 1
        return bloqueados, omitidos

    # ----------------------------------------------- operaciones por lote
    def bloquear_varios(self, cupos, motivo: str, usuario) -> tuple[int, int]:
        """Bloquea los cupos seleccionados. Los que tienen cita siguen ocupados (no se bloquean)."""
        roles.exigir_rol(usuario, roles.ADMINISTRACION, roles.TENS)
        bloqueados = omitidos = 0
        for cupo in cupos:
            if cupo.bloqueado:
                continue
            try:
                self.bloquear_cupo(cupo, motivo, usuario)
                bloqueados += 1
            except ReglaNegocioError:
                omitidos += 1
        return bloqueados, omitidos

    def liberar_varios(self, cupos, usuario, maximo: int | None = None) -> int:
        """Libera los cupos bloqueados seleccionados; «de a poco» = como máximo `maximo` por vez."""
        roles.exigir_rol(usuario, roles.ADMINISTRACION, roles.TENS)
        bloqueados = sorted((c for c in cupos if c.bloqueado), key=lambda c: (c.fecha, c.hora_inicio))
        if maximo:
            bloqueados = bloqueados[:maximo]
        for cupo in bloqueados:
            self.liberar_cupo(cupo, usuario)
        return len(bloqueados)

    @transaction.atomic
    def agregar_bloque(self, agenda: Agenda, usuario, semanas: int | None = None) -> tuple[Agenda, int]:
        """Crea el bloque semanal y genera sus cupos para las próximas semanas."""
        agenda = self.guardar_agenda(agenda, usuario)
        hoy = timezone.localdate()
        n = self.generar_cupos(agenda, hoy, hoy + timedelta(weeks=semanas or settings.AGENDA_SEMANAS_GENERACION), usuario)
        return agenda, n

    @transaction.atomic
    def quitar_bloque(self, agenda: Agenda, usuario) -> int:
        """
        Desactiva el bloque semanal. Sus cupos futuros sin citas se eliminan; los que
        tienen citas se mantienen (las citas siguen vigentes) pero quedan bloqueados.
        """
        roles.exigir_rol(usuario, roles.ADMINISTRACION)
        hoy = timezone.localdate()
        agenda.activa = False
        agenda.vigente_hasta = hoy
        agenda.save()
        eliminados = 0
        for cupo in Cupo.objects.select_for_update().filter(agenda=agenda, fecha__gt=hoy):
            if cupo.citas.exists():
                if not cupo.citas.filter(estado__in=["agendada", "confirmada", "sin_respuesta"]).exists():
                    cupo.bloqueado, cupo.motivo_bloqueo = True, "Bloque semanal eliminado"
                    cupo.save()
            else:
                cupo.delete()
                eliminados += 1
        return eliminados

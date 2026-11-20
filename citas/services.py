"""Servicios del módulo Citas: AgendamientoService y ConfirmacionService."""
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from agenda.models import Cupo
from core import roles
from core.exceptions import ReglaNegocioError
from pacientes.models import Paciente

from . import notificaciones as plantillas
from .models import Cita, MensajeEnviado
from .notificaciones import INotificador, NotificadorLog
from .repositories import CitaRepositoryPostgres, ICitaRepository

Estado = Cita.Estado


@dataclass
class ResultadoAgendamiento:
    citas: list[Cita]
    advertencias: list[str] = field(default_factory=list)


class AgendamientoService:
    """Disponibilidad, agendamiento (normal, varias sesiones y sobrecupo) y cancelación."""

    def __init__(self, repo: ICitaRepository | None = None, notificador: INotificador | None = None):
        self.repo = repo or CitaRepositoryPostgres()
        self.notificador = notificador or NotificadorLog()

    # ---------------------------------------------------------- consultas
    def disponibilidad(self, desde, hasta=None, especialidad=None, profesional=None, policlinico=None):
        filtros = {"desde": desde, "hasta": hasta or desde, "especialidad": especialidad,
                   "profesional": profesional, "policlinico": policlinico}
        return {
            "libres": list(self.repo.cupos_libres(filtros)),
            "sobrecupo": list(self.repo.cupos_para_sobrecupo(filtros)),
        }

    @staticmethod
    def max_sesiones(cupo: Cupo) -> int:
        esp = cupo.agenda.profesional.especialidad
        return esp.sesiones_por_tratamiento if esp.permite_agendar_todas_sesiones else 1

    # ------------------------------------------------------------ comandos
    def agendar(self, paciente: Paciente, cupo: Cupo, usuario, sesiones: int = 1,
                dias_aviso: int | None = None, observaciones: str = "") -> ResultadoAgendamiento:
        """
        RN-01: agenda sobre un cupo disponible. Si la especialidad lo permite,
        agenda todas las sesiones de una vez (todo o nada, en una transacción).
        """
        roles.exigir_rol(usuario, roles.TENS)  # solo TENS/TONS registran citas
        sesiones = max(1, int(sesiones or 1))
        maximo = self.max_sesiones(cupo)
        if sesiones > maximo:
            esp = cupo.agenda.profesional.especialidad
            raise ReglaNegocioError(
                f"{esp.nombre} permite agendar como máximo {maximo} sesión(es) de una vez.", "RN-01"
            )
        datos = {"observaciones": observaciones}
        if dias_aviso is not None:
            datos["dias_aviso"] = dias_aviso

        with transaction.atomic():
            cupos = [cupo]
            if sesiones > 1:
                siguientes = self.repo.siguientes_cupos_libres(cupo, sesiones - 1)
                if len(siguientes) < sesiones - 1:
                    raise ReglaNegocioError(
                        f"Solo hay {len(siguientes) + 1} cupos disponibles para {sesiones} sesiones "
                        f"(mismo profesional, policlínico y hora). Genere más cupos o agende menos sesiones.",
                        "RN-01",
                    )
                cupos += siguientes
                datos.update(grupo_sesiones=uuid.uuid4(), total_sesiones=sesiones)
            citas = [
                self.repo.crear_cita(c.pk, paciente, usuario, numero_sesion=i, **datos)
                for i, c in enumerate(cupos, 1)
            ]
            self.notificador.enviar(paciente, plantillas.mensaje_agendamiento(citas),
                                    MensajeEnviado.Tipo.AGENDAMIENTO, citas[0], usuario)
        return ResultadoAgendamiento(citas, paciente.advertencias)

    def agendar_sobrecupo(self, paciente: Paciente, cupo: Cupo, usuario, dias_aviso: int | None = None,
                          observaciones: str = "") -> ResultadoAgendamiento:
        """RN-07: sobrecupo solo cuando la cita del cupo está sin respuesta (máx. 2 citas por cupo)."""
        roles.exigir_rol(usuario, roles.TENS)
        datos = {"observaciones": observaciones}
        if dias_aviso is not None:
            datos["dias_aviso"] = dias_aviso
        with transaction.atomic():
            cita = self.repo.crear_sobrecupo(cupo.pk, paciente, usuario, **datos)
            self.notificador.enviar(paciente, plantillas.mensaje_agendamiento([cita]),
                                    MensajeEnviado.Tipo.AGENDAMIENTO, cita, usuario)
        return ResultadoAgendamiento([cita], paciente.advertencias)

    def cancelar(self, cita: Cita, usuario, motivo: str = "", notificar: bool = True) -> Cita:
        """Cancela la cita y libera el cupo por completo."""
        roles.exigir_rol(usuario, roles.TENS)
        with transaction.atomic():
            cancelada = self.repo.cancelar(cita.pk, usuario, motivo or "Cancelada")
            if notificar:
                self.notificador.enviar(cita.paciente, plantillas.mensaje_cancelacion(cita),
                                        MensajeEnviado.Tipo.CANCELACION, cita, usuario)
        return cancelada


class ConfirmacionService:
    """Recordatorios (diasAviso) y respuesta del paciente: confirma, cancela o no responde."""

    def __init__(self, repo: ICitaRepository | None = None, notificador: INotificador | None = None,
                 agendamiento: AgendamientoService | None = None):
        self.repo = repo or CitaRepositoryPostgres()
        self.notificador = notificador or NotificadorLog()
        self.agendamiento = agendamiento or AgendamientoService(self.repo, self.notificador)

    def recordatorios_pendientes(self, hoy=None) -> list[Cita]:
        """Citas agendadas cuyo aviso corresponde hoy o ya pasó y aún no se ha enviado."""
        hoy = hoy or timezone.localdate()
        candidatas = self.repo.listar(fecha_desde=hoy, fecha_hasta=hoy + timedelta(days=60),
                                      estado=Estado.AGENDADA).filter(recordatorio_enviado_en__isnull=True)
        return [c for c in candidatas if c.fecha_aviso <= hoy]

    def esperando_respuesta(self, hoy=None):
        hoy = hoy or timezone.localdate()
        return self.repo.listar(fecha_desde=hoy, estado=Estado.AGENDADA).filter(recordatorio_enviado_en__isnull=False)

    def enviar_recordatorio(self, cita: Cita, usuario) -> None:
        roles.exigir_rol(usuario, roles.TENS)
        if cita.estado not in (Estado.AGENDADA, Estado.SIN_RESPUESTA):
            raise ReglaNegocioError("Solo se envían recordatorios a citas agendadas o sin respuesta.", "ESTADO")
        with transaction.atomic():
            self.repo.marcar_recordatorio(cita.pk)
            self.notificador.enviar(cita.paciente, plantillas.mensaje_recordatorio(cita),
                                    MensajeEnviado.Tipo.RECORDATORIO, cita, usuario)

    def registrar_confirmacion(self, cita: Cita, usuario) -> Cita:
        """El paciente confirma (simulado desde la interfaz)."""
        roles.exigir_rol(usuario, roles.TENS)
        with transaction.atomic():
            cita = self.repo.cambiar_estado(cita.pk, Estado.CONFIRMADA, (Estado.AGENDADA, Estado.SIN_RESPUESTA),
                                            respuesta_en=timezone.now())
            self.notificador.enviar(cita.paciente, plantillas.mensaje_confirmacion(cita),
                                    MensajeEnviado.Tipo.CONFIRMACION, cita, usuario)
        return cita

    def registrar_cancelacion(self, cita: Cita, usuario, motivo: str = "Cancelada por el paciente") -> Cita:
        """El paciente cancela (simulado): se libera el cupo."""
        return self.agendamiento.cancelar(cita, usuario, motivo)

    def marcar_sin_respuesta(self, cita: Cita, usuario) -> Cita:
        """El paciente no respondió: habilita el sobrecupo (RN-07)."""
        roles.exigir_rol(usuario, roles.TENS)
        return self.repo.cambiar_estado(cita.pk, Estado.SIN_RESPUESTA, (Estado.AGENDADA,))


def resumen_del_dia(usuario) -> dict | None:
    """Indicadores para el panel de inicio."""
    if not roles.tiene_rol(usuario, roles.TENS, roles.ADMINISTRACION, roles.PROFESIONAL):
        return None
    hoy = timezone.localdate()
    qs = Cita.objects.filter(cupo__fecha__gte=hoy)
    if not roles.tiene_rol(usuario, roles.TENS, roles.ADMINISTRACION):
        prof = getattr(usuario, "profesional", None)
        qs = qs.filter(cupo__agenda__profesional=prof) if prof else qs.none()
    datos = qs.aggregate(
        citas_hoy=Count("pk", filter=Q(cupo__fecha=hoy) & ~Q(estado=Estado.CANCELADA)),
        confirmadas_hoy=Count("pk", filter=Q(cupo__fecha=hoy, estado=Estado.CONFIRMADA)),
        sin_respuesta=Count("pk", filter=Q(estado=Estado.SIN_RESPUESTA)),
    )
    datos["recordatorios_pendientes"] = (
        len(ConfirmacionService().recordatorios_pendientes()) if roles.tiene_rol(usuario, roles.TENS) else "—"
    )
    return datos

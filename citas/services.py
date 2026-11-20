"""Servicios del módulo Citas: AgendamientoService y ConfirmacionService."""
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from agenda.models import Cupo
from core import roles
from core.exceptions import ReglaNegocioError, TransicionEstadoInvalidaError
from pacientes.models import Paciente

from . import notificaciones as avisos
from .models import Cita, MensajeEnviado
from .notificaciones import INotificador, NotificadorLog
from .repositories import CitaRepositoryPostgres, ICitaRepository

Estado = Cita.Estado


@dataclass
class ResultadoAgendamiento:
    citas: list[Cita]
    advertencias: list[str] = field(default_factory=list)


def _exigir_policlinico(usuario, *cupos) -> None:
    """La TENS/TONS solo opera sobre citas y horas de su propio policlínico."""
    for cupo in cupos:
        roles.exigir_policlinico(usuario, cupo.agenda.policlinico_id)


def _marcar_lista_espera(cita: Cita) -> None:
    """Si el paciente estaba en lista de espera para esa especialidad, queda como «agendado»."""
    from lista_espera.services import ListaEsperaService

    ListaEsperaService().marcar_agendado(cita)


class AgendamientoService:
    """Disponibilidad, agendamiento (TENS o el paciente por web), sobrecupo, cancelación y cambio de hora."""

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

    def dias_con_horas(self, desde: date, hasta: date, **filtros) -> Counter:
        """{fecha: cantidad de horas libres} para pintar el calendario."""
        libres = self.repo.cupos_libres({"desde": desde, "hasta": hasta, **filtros})
        return Counter(libres.values_list("fecha", flat=True))

    @staticmethod
    def max_sesiones(cupo_o_especialidad) -> int:
        esp = getattr(cupo_o_especialidad, "agenda", None)
        esp = esp.profesional.especialidad if esp else cupo_o_especialidad
        return esp.sesiones_por_tratamiento if esp.permite_agendar_todas_sesiones else 1

    # ------------------------------------------------------------ comandos
    def _agendar(self, paciente, cupo, usuario, sesiones, datos) -> ResultadoAgendamiento:
        sesiones = max(1, int(sesiones or 1))
        maximo = self.max_sesiones(cupo)
        if sesiones > maximo:
            esp = cupo.agenda.profesional.especialidad
            raise ReglaNegocioError(f"{esp.nombre} permite agendar como máximo {maximo} sesión(es) de una vez.")
        with transaction.atomic():
            cupos = [cupo]
            if sesiones > 1:
                siguientes = self.repo.siguientes_cupos_libres(cupo, sesiones - 1)
                if len(siguientes) < sesiones - 1:
                    raise ReglaNegocioError(
                        f"Solo hay {len(siguientes) + 1} horas disponibles para {sesiones} sesiones "
                        f"(mismo profesional, policlínico y hora). Agende menos sesiones.")
                cupos += siguientes
                datos = {**datos, "grupo_sesiones": uuid.uuid4(), "total_sesiones": sesiones}
            citas = [self.repo.crear_cita(c.pk, paciente, usuario, numero_sesion=i, **datos)
                     for i, c in enumerate(cupos, 1)]
            self.notificador.enviar(paciente, avisos.aviso_agendamiento(citas), citas[0], usuario)
            _marcar_lista_espera(citas[0])
        return ResultadoAgendamiento(citas, paciente.advertencias)

    def agendar(self, paciente: Paciente, cupo: Cupo, usuario, sesiones: int = 1, dias_aviso: int | None = None,
                observaciones: str = "", canal: str = Cita.Canal.PRESENCIAL) -> ResultadoAgendamiento:
        """RN-01: la TENS agenda sobre un cupo disponible (y, si la especialidad lo permite, todas las sesiones)."""
        roles.exigir_rol(usuario, roles.TENS)
        _exigir_policlinico(usuario, cupo)
        datos = {"observaciones": observaciones, "canal": canal}
        if dias_aviso is not None:
            datos["dias_aviso"] = dias_aviso
        return self._agendar(paciente, cupo, usuario, sesiones, datos)

    def agendar_web(self, paciente: Paciente, cupo: Cupo) -> ResultadoAgendamiento:
        """El paciente reserva su hora desde el portal web, sin cuenta (una sesión, sin sobrecupo)."""
        return self._agendar(paciente, cupo, None, 1, {"canal": Cita.Canal.WEB})

    def agendar_sobrecupo(self, paciente: Paciente, cupo: Cupo, usuario, dias_aviso: int | None = None,
                          observaciones: str = "", canal: str = Cita.Canal.PRESENCIAL) -> ResultadoAgendamiento:
        """RN-07: sobrecupo solo cuando la cita del cupo está sin respuesta (máx. 2 citas por cupo)."""
        roles.exigir_rol(usuario, roles.TENS)
        _exigir_policlinico(usuario, cupo)
        datos = {"observaciones": observaciones, "canal": canal}
        if dias_aviso is not None:
            datos["dias_aviso"] = dias_aviso
        with transaction.atomic():
            cita = self.repo.crear_sobrecupo(cupo.pk, paciente, usuario, **datos)
            self.notificador.enviar(paciente, avisos.aviso_agendamiento([cita]), cita, usuario)
            _marcar_lista_espera(cita)
        return ResultadoAgendamiento([cita], paciente.advertencias)

    def cancelar(self, cita: Cita, usuario, motivo: str = "", por_paciente: bool = False) -> Cita:
        """Cancela la cita y libera el cupo por completo. La TENS o el propio paciente (link del aviso)."""
        if not por_paciente:
            roles.exigir_rol(usuario, roles.TENS)
            _exigir_policlinico(usuario, cita.cupo)
        with transaction.atomic():
            cancelada = self.repo.cancelar(cita.pk, usuario, motivo or "Cancelada",
                                           origen="paciente" if por_paciente else "tens")
            self.notificador.enviar(cita.paciente, avisos.aviso_cancelacion(cita), cita, usuario)
        return cancelada

    def reagendar(self, cita: Cita, nuevo_cupo: Cupo, usuario=None, por_paciente: bool = False,
                  es_sobrecupo: bool = False) -> Cita:
        """
        Cambia la hora: en una sola transacción se cancela la cita actual (su cupo
        queda libre) y se crea la nueva. Si algo falla, no cambia nada.
        """
        if not por_paciente:
            roles.exigir_rol(usuario, roles.TENS)
            _exigir_policlinico(usuario, cita.cupo, nuevo_cupo)
        if not cita.es_vigente:
            raise TransicionEstadoInvalidaError("Solo se pueden cambiar citas vigentes.")
        if nuevo_cupo.pk == cita.cupo_id:
            raise ReglaNegocioError("La nueva hora es igual a la actual.", "CAMBIO")
        datos = {"dias_aviso": cita.dias_aviso, "observaciones": cita.observaciones,
                 "canal": Cita.Canal.WEB if por_paciente else cita.canal}
        with transaction.atomic():
            self.repo.cancelar(cita.pk, usuario, "Hora cambiada")
            if es_sobrecupo:
                nueva = self.repo.crear_sobrecupo(nuevo_cupo.pk, cita.paciente, usuario, **datos)
            else:
                nueva = self.repo.crear_cita(nuevo_cupo.pk, cita.paciente, usuario, **datos)
            self.notificador.enviar(cita.paciente, avisos.aviso_cambio(nueva), nueva, usuario)
        return nueva


class ConfirmacionService:
    """Avisos (diasAviso antes) y respuesta del paciente: confirma, cancela, cambia o no responde."""

    def __init__(self, repo: ICitaRepository | None = None, notificador: INotificador | None = None,
                 agendamiento: AgendamientoService | None = None):
        self.repo = repo or CitaRepositoryPostgres()
        self.notificador = notificador or NotificadorLog()
        self.agendamiento = agendamiento or AgendamientoService(self.repo, self.notificador)

    # ---------------------------------------------------------- consultas
    def citas_del_dia(self, fecha: date):
        return (self.repo.listar(fecha_desde=fecha, fecha_hasta=fecha)
                .prefetch_related("mensajes").select_related("asistencia")
                .order_by("cupo__hora_inicio", "es_sobrecupo"))

    def recordatorios_pendientes(self, hoy=None) -> list[Cita]:
        """Citas agendadas cuyo aviso (fecha - diasAviso) ya corresponde y que no lo han recibido."""
        hoy = hoy or timezone.localdate()
        candidatas = (self.repo.listar(fecha_desde=hoy, fecha_hasta=hoy + timedelta(days=30), estado=Estado.AGENDADA)
                      .prefetch_related("mensajes"))
        return [c for c in candidatas if c.fecha_aviso <= hoy and c.estado_aviso != "enviado"]

    # ------------------------------------------------------------ comandos
    def enviar_recordatorio(self, cita: Cita, usuario) -> bool:
        """
        Envía (o reintenta) el aviso por correo y por WhatsApp, cuando es posible.
        Devuelve True si salió por al menos un medio.
        """
        roles.exigir_rol(usuario, roles.TENS)
        _exigir_policlinico(usuario, cita.cupo)
        if cita.estado not in (Estado.AGENDADA, Estado.SIN_RESPUESTA):
            raise ReglaNegocioError("Solo se envían avisos a citas agendadas o sin respuesta.", "ESTADO")
        with transaction.atomic():
            envios = self.notificador.enviar(cita.paciente, avisos.aviso_recordatorio(cita), cita, usuario)
            ok = any(e.estado == MensajeEnviado.Estado.ENVIADO for e in envios)
            if ok:
                self.repo.marcar_recordatorio(cita.pk)
        return ok

    def enviar_pendientes(self, usuario) -> tuple[int, int]:
        enviados = fallidos = 0
        pol = roles.policlinico_de(usuario)
        for cita in self.recordatorios_pendientes():
            if pol and cita.cupo.agenda.policlinico_id != pol.pk:
                continue
            if self.enviar_recordatorio(cita, usuario):
                enviados += 1
            else:
                fallidos += 1
        return enviados, fallidos

    def registrar_confirmacion(self, cita: Cita, usuario=None, por_paciente: bool = False) -> Cita:
        """El paciente confirma desde el link del aviso (queda registrado solo) o la TENS lo registra."""
        if not por_paciente:
            roles.exigir_rol(usuario, roles.TENS)
            _exigir_policlinico(usuario, cita.cupo)
        with transaction.atomic():
            cita = self.repo.cambiar_estado(cita.pk, Estado.CONFIRMADA, (Estado.AGENDADA, Estado.SIN_RESPUESTA),
                                            respuesta_en=timezone.now(),
                                            respuesta_origen="paciente" if por_paciente else "tens")
            self.notificador.enviar(cita.paciente, avisos.aviso_confirmacion(cita), cita, usuario)
        return cita

    def registrar_cancelacion(self, cita: Cita, usuario=None, motivo: str = "Cancelada por el paciente",
                              por_paciente: bool = False) -> Cita:
        """El paciente cancela (por el link o avisando a la TENS): se libera el cupo."""
        return self.agendamiento.cancelar(cita, usuario, motivo, por_paciente=por_paciente)

    def marcar_sin_respuesta(self, cita: Cita, usuario) -> Cita:
        """
        El paciente no respondió: habilita el sobrecupo (RN-07). La TENS también
        puede corregir una confirmación registrada por error.
        """
        roles.exigir_rol(usuario, roles.TENS)
        _exigir_policlinico(usuario, cita.cupo)
        return self.repo.cambiar_estado(cita.pk, Estado.SIN_RESPUESTA, (Estado.AGENDADA, Estado.CONFIRMADA),
                                        respuesta_en=timezone.now(), respuesta_origen="tens")

    def registrar_respuesta(self, cita: Cita, respuesta: str, usuario) -> Cita:
        """
        La TENS registra o cambia la respuesta (el paciente contestó por teléfono o
        en persona, o no contestó). Si es la misma respuesta actual, no cambia nada.
        """
        actual = {Estado.CONFIRMADA: "confirmar", Estado.SIN_RESPUESTA: "sin_respuesta"}.get(cita.estado)
        if respuesta == actual:
            return cita
        if respuesta == "confirmar":
            return self.registrar_confirmacion(cita, usuario)
        if respuesta == "cancelar":
            return self.registrar_cancelacion(cita, usuario, "Avisó a la TENS/TONS (teléfono o en persona)")
        if respuesta == "sin_respuesta":
            return self.marcar_sin_respuesta(cita, usuario)
        raise ReglaNegocioError("Respuesta no válida.", "ESTADO")


# ---------------------------------------------------------------- indicadores
def resumen_tens(hoy=None, policlinico=None) -> dict:
    """Indicadores del inicio de la TENS/TONS (solo de su policlínico)."""
    from lista_espera.models import SolicitudEspera

    hoy = hoy or timezone.localdate()
    manana = hoy + timedelta(days=1)
    while manana.weekday() >= 5:  # próximo día hábil
        manana += timedelta(days=1)
    citas = Cita.objects.all()
    espera = SolicitudEspera.objects.filter(estado__in=SolicitudEspera.ACTIVOS)
    if policlinico:
        citas = citas.filter(cupo__agenda__policlinico=policlinico)
        espera = espera.filter(policlinico=policlinico)
    proximas = (citas.filter(cupo__fecha__gte=hoy, cupo__fecha__lte=hoy + timedelta(days=7),
                             estado__in=Cita.VIGENTES).prefetch_related("mensajes"))
    return {
        "citas_hoy": citas.filter(cupo__fecha=hoy, estado__in=Cita.VIGENTES).count(),
        "por_confirmar_manana": citas.filter(
            cupo__fecha=manana, estado__in=(Estado.AGENDADA, Estado.SIN_RESPUESTA)).count(),
        "en_espera": espera.count(),
        "avisos_con_falla": sum(1 for c in proximas if c.estado_aviso == "fallido"),
        "sin_respuesta": citas.filter(cupo__fecha__gte=hoy, estado=Estado.SIN_RESPUESTA).count(),
    }


def contador_alertas(usuario) -> int:
    """Número de la campana: avisos con falla + citas sin respuesta (TENS) o lista de espera (Administración)."""
    if roles.tiene_rol(usuario, roles.TENS):
        r = resumen_tens(policlinico=roles.policlinico_de(usuario))
        return r["avisos_con_falla"] + r["sin_respuesta"]
    if roles.tiene_rol(usuario, roles.ADMINISTRACION):
        from lista_espera.models import SolicitudEspera

        return SolicitudEspera.objects.filter(estado__in=SolicitudEspera.ACTIVOS).count()
    return 0

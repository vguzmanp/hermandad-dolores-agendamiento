"""
Notificaciones a pacientes.

INotificador define el contrato. El aviso va por WhatsApp y, si el paciente tiene
correo (opcional), también por correo. Ambos traen el link /c/<código>/ para responder.
Cada envío queda registrado en MensajeEnviado (pantalla «Avisos enviados»).

- NotificadorLog: no envía nada, solo registra los mensajes.
- NotificadorCorreo: envía el correo por SMTP; el WhatsApp sigue registrado sin enviarse.

Se elige con ENVIAR_CORREOS en .env (ver notificador_configurado()).
"""
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import send_mail

from core.fechas import fecha_larga
from pacientes.models import Paciente

from .models import Cita, MensajeEnviado

Tipo = MensajeEnviado.Tipo
logger = logging.getLogger(__name__)


@dataclass
class Aviso:
    tipo: str
    whatsapp: str
    asunto: str
    correo: str


class INotificador(ABC):
    @abstractmethod
    def enviar(self, paciente: Paciente, aviso: Aviso, cita: Cita | None = None, usuario=None) -> list:
        """Envía el aviso al paciente (o a su adulto responsable). Devuelve los envíos realizados."""


def celular_valido(celular: str) -> bool:
    digitos = re.sub(r"\D", "", celular or "")
    return bool(re.fullmatch(r"(56)?9\d{8}", digitos))


class NotificadorLog(INotificador):
    def enviar(self, paciente, aviso, cita=None, usuario=None):
        nombre, celular = contacto(paciente)
        envios = [MensajeEnviado.objects.create(
            paciente=paciente, cita=cita, destinatario=f"{nombre} · {celular}",
            canal=MensajeEnviado.Canal.WHATSAPP,
            estado=MensajeEnviado.Estado.ENVIADO if celular_valido(celular) else MensajeEnviado.Estado.FALLIDO,
            tipo=aviso.tipo, mensaje=aviso.whatsapp, enviado_por=usuario,
        )]
        if paciente.correo:
            enviado = self.enviar_correo(paciente.correo, aviso)
            envios.append(MensajeEnviado.objects.create(
                paciente=paciente, cita=cita, destinatario=paciente.correo, canal=MensajeEnviado.Canal.CORREO,
                estado=MensajeEnviado.Estado.ENVIADO if enviado else MensajeEnviado.Estado.FALLIDO,
                tipo=aviso.tipo, asunto=aviso.asunto, mensaje=aviso.correo, enviado_por=usuario,
            ))
        return envios

    def enviar_correo(self, destino: str, aviso: Aviso) -> bool:
        """Sin envío real: el correo solo queda registrado."""
        return True


class NotificadorCorreo(NotificadorLog):
    """Envía el correo de verdad por SMTP. Si falla, queda como «No se pudo enviar» y la operación sigue."""

    def enviar_correo(self, destino: str, aviso: Aviso) -> bool:
        try:
            send_mail(aviso.asunto, aviso.correo, None, [destino], fail_silently=False)
            return True
        except Exception:
            logger.exception("No se pudo enviar el correo a %s", destino)
            return False


def notificador_configurado() -> INotificador:
    return NotificadorCorreo() if settings.ENVIAR_CORREOS else NotificadorLog()


def contacto(paciente: Paciente) -> tuple[str, str]:
    """Si corresponde adulto responsable (RN-04), el WhatsApp va dirigido a él/ella."""
    resp = getattr(paciente, "adulto_responsable", None) if paciente.necesita_responsable else None
    if resp:
        return f"{resp.nombre} ({resp.parentesco})", resp.celular
    return paciente.nombre, paciente.celular


# ------------------------------------------------------------------ plantillas
def link_cita(cita: Cita) -> str:
    return f"{settings.SITIO_PUBLICO_URL.rstrip('/')}/c/{cita.token}"


def _primer_nombre(paciente: Paciente) -> str:
    return paciente.nombre.split()[0]


def _quien(cita: Cita) -> str:
    prof = cita.cupo.agenda.profesional
    return f"{prof.especialidad.nombre} con {prof.nombre}"


def _lugar(cita: Cita) -> str:
    pol = cita.cupo.agenda.policlinico
    return "por videollamada (Telemedicina)" if pol.es_telemedicina else f"en el {pol.nombre}"


def _cuando(cita: Cita) -> str:
    return f"{fecha_larga(cita.cupo.fecha)} a las {cita.cupo.hora_inicio:%H:%M}"


def _ficha(cita: Cita) -> str:
    prof = cita.cupo.agenda.profesional
    return (f"Especialidad: {prof.especialidad.nombre}\nProfesional: {prof.nombre}\n"
            f"Policlínico: {cita.cupo.agenda.policlinico.nombre}\n"
            f"Fecha y hora: {fecha_larga(cita.cupo.fecha).capitalize()} · {cita.cupo.hora_inicio:%H:%M}")


def aviso_agendamiento(citas: list[Cita]) -> Aviso:
    c = citas[0]
    nombre = _primer_nombre(c.paciente)
    if len(citas) == 1:
        detalle = f"tu hora de {_quien(c)} quedó reservada para el {_cuando(c)} {_lugar(c)}."
    else:
        lineas = "\n".join(f"{i}. {fecha_larga(x.cupo.fecha)} a las {x.cupo.hora_inicio:%H:%M}"
                           for i, x in enumerate(citas, 1))
        detalle = f"se reservaron {len(citas)} sesiones de {_quien(c)} {_lugar(c)}:\n{lineas}"
    whatsapp = (f"Hola {nombre}, {detalle}\n\nTe enviaremos un recordatorio {c.dias_aviso} días antes para "
                f"confirmar tu asistencia.")
    correo = (f"Hola {nombre}:\n\nTu hora quedó reservada.\n\n{_ficha(c)}\n\n"
              f"Recuerda traer tu certificado de FONASA y la inscripción al CESFAM.")
    return Aviso(Tipo.AGENDAMIENTO, whatsapp, f"Hora reservada para el {fecha_larga(c.cupo.fecha)}", correo)


def aviso_recordatorio(cita: Cita) -> Aviso:
    nombre = _primer_nombre(cita.paciente)
    whatsapp = (f"Hola {nombre}, te recordamos tu hora de {_quien(cita)} el {_cuando(cita)}.\n\n"
                f"Por favor confirma si asistirás, o cambia o cancela tu hora aquí:\n{link_cita(cita)}")
    correo = (f"Hola {nombre}:\n\nTe recordamos que tienes una hora agendada. Por favor confírmanos si podrás asistir."
              f"\n\n{_ficha(cita)}\n\nConfirmar o cambiar mi hora: {link_cita(cita)}\n"
              f"Si no respondes, la cita queda como «sin respuesta» y te llamaremos.")
    return Aviso(Tipo.RECORDATORIO, whatsapp, f"Confirma tu hora del {fecha_larga(cita.cupo.fecha)}", correo)


def aviso_confirmacion(cita: Cita) -> Aviso:
    texto = f"Asistencia confirmada. Te esperamos el {_cuando(cita)} ({_quien(cita)})."
    return Aviso(Tipo.CONFIRMACION, f"Hola {_primer_nombre(cita.paciente)}. {texto}", "Asistencia confirmada",
                 f"{texto}\n\nRecuerda traer tu certificado de FONASA y la inscripción al CESFAM.")


def aviso_cancelacion(cita: Cita) -> Aviso:
    texto = (f"Tu hora del {_cuando(cita)} ({_quien(cita)}) fue cancelada y quedó libre para otro paciente. "
             f"Si necesitas atención, puedes reservar una nueva hora.")
    return Aviso(Tipo.CANCELACION, f"Hola {_primer_nombre(cita.paciente)}. {texto}", "Hora cancelada", texto)


def aviso_bloqueo(cita: Cita) -> Aviso:
    """La hora se bloqueó (el profesional no atenderá): la cita queda cancelada."""
    nombre = _primer_nombre(cita.paciente)
    reservar = f"{settings.SITIO_PUBLICO_URL.rstrip('/')}/reservar/"
    whatsapp = (f"Hola {nombre}, lamentamos avisarte que tu hora de {_quien(cita)} del {_cuando(cita)} fue "
                f"cancelada porque el profesional no podrá atender en ese horario.\n\n"
                f"Puedes reservar una nueva hora aquí: {reservar}")
    correo = (f"Hola {nombre}:\n\nLamentamos avisarte que tu hora fue cancelada porque el profesional no podrá "
              f"atender en ese horario.\n\n{_ficha(cita)}\n\n"
              f"Puedes reservar una nueva hora aquí: {reservar}\no comunicarte con el policlínico.")
    return Aviso(Tipo.CANCELACION, whatsapp, f"Tu hora del {fecha_larga(cita.cupo.fecha)} fue cancelada", correo)


def aviso_cambio(cita: Cita) -> Aviso:
    texto = f"Tu nueva hora es el {_cuando(cita)} con {cita.cupo.agenda.profesional.nombre}."
    return Aviso(Tipo.CAMBIO, f"Hola {_primer_nombre(cita.paciente)}. {texto}\n{link_cita(cita)}", "Hora cambiada",
                 f"{texto}\n\n{_ficha(cita)}\n\n{link_cita(cita)}")

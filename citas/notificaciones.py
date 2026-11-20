"""
Notificaciones a pacientes.

WhatsApp NO se integra en el MVP: se define la interfaz INotificador y una
implementación NotificadorLog que guarda cada mensaje en la base de datos para
mostrarlo en la pantalla "Mensajes enviados". Para integrar WhatsApp a futuro
basta con otra implementación de INotificador (p. ej. NotificadorWhatsApp).
"""
from abc import ABC, abstractmethod

from pacientes.models import Paciente

from .models import Cita, MensajeEnviado


class INotificador(ABC):
    @abstractmethod
    def enviar(self, paciente: Paciente, mensaje: str, tipo: str, cita: Cita | None = None, usuario=None):
        """Envía un mensaje al paciente (o a su adulto responsable)."""


class NotificadorLog(INotificador):
    def enviar(self, paciente, mensaje, tipo, cita=None, usuario=None) -> MensajeEnviado:
        return MensajeEnviado.objects.create(
            paciente=paciente, cita=cita, destinatario=destinatario(paciente),
            tipo=tipo, mensaje=mensaje, enviado_por=usuario,
        )


def destinatario(paciente: Paciente) -> str:
    """Si corresponde adulto responsable (RN-04), el mensaje va dirigido a él/ella."""
    resp = getattr(paciente, "adulto_responsable", None) if paciente.necesita_responsable else None
    if resp:
        return f"{resp.nombre} ({resp.parentesco}) · {resp.celular}"
    return f"{paciente.nombre} · {paciente.celular}"


# ------------------------------------------------------------------ plantillas
def _detalle(cita: Cita) -> str:
    c = cita.cupo
    lugar = "por videollamada (Telemedicina)" if c.agenda.policlinico.es_telemedicina else f"en {c.agenda.policlinico.nombre}"
    return (f"{c.fecha:%d/%m/%Y} a las {c.hora_inicio:%H:%M} con {c.agenda.profesional.nombre} "
            f"({c.agenda.profesional.especialidad.nombre}) {lugar}")


def mensaje_agendamiento(citas: list[Cita]) -> str:
    p = citas[0].paciente
    if len(citas) == 1:
        cuerpo = f"se agendó su cita para el {_detalle(citas[0])}."
    else:
        lineas = "\n".join(f"  {i}. {_detalle(c)}" for i, c in enumerate(citas, 1))
        cuerpo = f"se agendaron {len(citas)} sesiones:\n{lineas}"
    sobre = " (sobrecupo)" if citas[0].es_sobrecupo else ""
    return (f"Hermandad de Dolores: Hola {p.nombre.split()[0]}, {cuerpo}{sobre}\n"
            f"Le enviaremos un recordatorio {citas[0].dias_aviso} días antes para confirmar su asistencia.")


def mensaje_recordatorio(cita: Cita) -> str:
    return (f"Hermandad de Dolores: Recordatorio de su cita el {_detalle(cita)}.\n"
            f"Responda 1 para CONFIRMAR o 2 para CANCELAR.")


def mensaje_confirmacion(cita: Cita) -> str:
    return f"Hermandad de Dolores: Su asistencia a la cita del {_detalle(cita)} quedó CONFIRMADA. ¡Le esperamos!"


def mensaje_cancelacion(cita: Cita) -> str:
    return (f"Hermandad de Dolores: Su cita del {_detalle(cita)} fue CANCELADA. "
            f"Si necesita reagendar, comuníquese con nosotros.")

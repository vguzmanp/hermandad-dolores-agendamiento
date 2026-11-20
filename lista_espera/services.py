"""
ListaEsperaService: orden de llegada por especialidad y policlínico (nunca por
profesional). La TENS/TONS puede subir manualmente a un paciente.
"""
from django.db import transaction
from django.db.models import Count, Max, Q

from core import roles
from core.exceptions import ReglaNegocioError

from .models import SolicitudEspera

Estado = SolicitudEspera.Estado


class ListaEsperaRepository:
    def base(self):
        return SolicitudEspera.objects.select_related("paciente", "especialidad", "policlinico", "creada_por")

    def listar(self, especialidad=None, policlinico=None, estado=None):
        qs = self.base()
        if especialidad:
            qs = qs.filter(especialidad=especialidad)
        if policlinico:
            qs = qs.filter(policlinico=policlinico)
        if estado:
            qs = qs.filter(estado=estado)
        else:
            qs = qs.exclude(estado=Estado.RETIRADO)
        return qs

    def siguiente_orden(self) -> int:
        return (SolicitudEspera.objects.aggregate(m=Max("orden"))["m"] or 0) + 1

    def activa_de(self, paciente, especialidad, policlinico=None):
        qs = SolicitudEspera.objects.filter(paciente=paciente, especialidad=especialidad,
                                            estado__in=SolicitudEspera.ACTIVOS)
        if policlinico is not None:
            qs = qs.filter(policlinico=policlinico)
        return qs.first()


def posiciones(solicitudes) -> dict[int, int]:
    """Posición de cada solicitud activa dentro de su lista (especialidad + policlínico)."""
    contador, res = {}, {}
    for s in sorted((s for s in solicitudes if s.activa), key=lambda s: (s.orden, s.creada_en)):
        clave = (s.especialidad_id, s.policlinico_id)
        contador[clave] = contador.get(clave, 0) + 1
        res[s.pk] = contador[clave]
    return res


class ListaEsperaService:
    def __init__(self, repo: ListaEsperaRepository | None = None):
        self.repo = repo or ListaEsperaRepository()

    def anotar(self, paciente, especialidad, policlinico, canal="presencial", usuario=None) -> SolicitudEspera:
        """
        Anota al paciente al final de la lista de la especialidad en ese policlínico
        (orden de llegada). Desde la web o por la TENS/TONS.
        """
        if policlinico is None:
            raise ReglaNegocioError("Indique el policlínico de la lista de espera.")
        if usuario is not None:
            roles.exigir_rol(usuario, roles.TENS)
            roles.exigir_policlinico(usuario, policlinico)
        if not policlinico.especialidades.filter(pk=especialidad.pk).exists():
            raise ReglaNegocioError(f"{especialidad.nombre} no se atiende en el {policlinico.nombre}.")
        existente = self.repo.activa_de(paciente, especialidad, policlinico)
        if existente:
            return existente
        return SolicitudEspera.objects.create(
            paciente=paciente, especialidad=especialidad, policlinico=policlinico,
            canal=canal, creada_por=usuario, orden=self.repo.siguiente_orden(),
        )

    @transaction.atomic
    def subir(self, solicitud: SolicitudEspera, usuario) -> bool:
        """Mueve al paciente un lugar hacia adelante dentro de su lista (especialidad + policlínico)."""
        roles.exigir_rol(usuario, roles.TENS)
        roles.exigir_policlinico(usuario, solicitud.policlinico_id)
        solicitud = SolicitudEspera.objects.select_for_update().get(pk=solicitud.pk)
        if not solicitud.activa:
            raise ReglaNegocioError("Solo se puede subir a pacientes que siguen esperando.")
        anterior = (SolicitudEspera.objects.select_for_update()
                    .filter(estado__in=SolicitudEspera.ACTIVOS, orden__lt=solicitud.orden,
                            especialidad_id=solicitud.especialidad_id, policlinico_id=solicitud.policlinico_id)
                    .order_by("-orden").first())
        if anterior is None:
            return False
        anterior.orden, solicitud.orden = solicitud.orden, anterior.orden
        anterior.save(update_fields=["orden"])
        solicitud.save(update_fields=["orden"])
        return True

    def actualizar_estado(self, solicitud: SolicitudEspera, estado: str, resultado: str, nota: str, usuario):
        roles.exigir_rol(usuario, roles.TENS)
        roles.exigir_policlinico(usuario, solicitud.policlinico_id)
        solicitud.estado = estado
        solicitud.resultado_contacto = resultado
        solicitud.nota = nota
        solicitud.save()
        return solicitud

    def marcar_agendado(self, cita) -> None:
        """Al agendar, la solicitud de esa especialidad en ese policlínico queda como «agendado»."""
        sol = self.repo.activa_de(cita.paciente, cita.cupo.agenda.profesional.especialidad,
                                  cita.cupo.agenda.policlinico)
        if sol:
            sol.estado, sol.cita = Estado.AGENDADO, cita
            sol.save(update_fields=["estado", "cita", "actualizada_en"])

    def resumen(self, policlinico=None) -> dict:
        qs = SolicitudEspera.objects.all()
        if policlinico:
            qs = qs.filter(policlinico=policlinico)
        return qs.aggregate(
            en_espera=Count("pk", filter=Q(estado=Estado.EN_ESPERA)),
            contactados=Count("pk", filter=Q(estado=Estado.CONTACTADO)),
            sin_contacto=Count("pk", filter=Q(estado=Estado.SIN_CONTACTO)),
            agendados=Count("pk", filter=Q(estado=Estado.AGENDADO)),
        )

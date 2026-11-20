"""ListaEsperaService — RN-06: orden de llegada; la TENS puede subir manualmente a un paciente."""
from django.db import transaction
from django.db.models import Count, Max, Q

from core import roles
from core.exceptions import ReglaNegocioError

from .models import SolicitudEspera

Estado = SolicitudEspera.Estado


class ListaEsperaRepository:
    def base(self):
        return SolicitudEspera.objects.select_related(
            "paciente", "especialidad", "profesional", "policlinico", "creada_por")

    def listar(self, especialidad=None, estado=None):
        qs = self.base()
        if especialidad:
            qs = qs.filter(especialidad=especialidad)
        if estado:
            qs = qs.filter(estado=estado)
        else:
            qs = qs.exclude(estado=Estado.RETIRADO)
        return qs

    def siguiente_orden(self) -> int:
        return (SolicitudEspera.objects.aggregate(m=Max("orden"))["m"] or 0) + 1

    def activa_de(self, paciente, especialidad):
        return SolicitudEspera.objects.filter(paciente=paciente, especialidad=especialidad,
                                              estado__in=SolicitudEspera.ACTIVOS).first()


class ListaEsperaService:
    def __init__(self, repo: ListaEsperaRepository | None = None):
        self.repo = repo or ListaEsperaRepository()

    def anotar(self, paciente, especialidad, profesional=None, policlinico=None, canal="presencial",
               usuario=None) -> SolicitudEspera:
        """Anota al paciente al final de la lista (orden de llegada). Desde la web o por la TENS."""
        if usuario is not None:
            roles.exigir_rol(usuario, roles.TENS)
        existente = self.repo.activa_de(paciente, especialidad)
        if existente:
            return existente
        return SolicitudEspera.objects.create(
            paciente=paciente, especialidad=especialidad, profesional=profesional, policlinico=policlinico,
            canal=canal, creada_por=usuario, orden=self.repo.siguiente_orden(),
        )

    @transaction.atomic
    def subir(self, solicitud: SolicitudEspera, usuario) -> bool:
        """Mueve al paciente un lugar hacia adelante (intercambia el orden con el anterior activo)."""
        roles.exigir_rol(usuario, roles.TENS)
        solicitud = SolicitudEspera.objects.select_for_update().get(pk=solicitud.pk)
        if not solicitud.activa:
            raise ReglaNegocioError("Solo se puede subir a pacientes que siguen esperando.", "RN-06")
        anterior = (SolicitudEspera.objects.select_for_update()
                    .filter(estado__in=SolicitudEspera.ACTIVOS, orden__lt=solicitud.orden)
                    .order_by("-orden").first())
        if anterior is None:
            return False
        anterior.orden, solicitud.orden = solicitud.orden, anterior.orden
        anterior.save(update_fields=["orden"])
        solicitud.save(update_fields=["orden"])
        return True

    def actualizar_estado(self, solicitud: SolicitudEspera, estado: str, resultado: str, nota: str, usuario):
        roles.exigir_rol(usuario, roles.TENS)
        solicitud.estado = estado
        solicitud.resultado_contacto = resultado
        solicitud.nota = nota
        solicitud.save()
        return solicitud

    def marcar_agendado(self, cita) -> None:
        esp = cita.cupo.agenda.profesional.especialidad
        sol = self.repo.activa_de(cita.paciente, esp)
        if sol:
            sol.estado, sol.cita = Estado.AGENDADO, cita
            sol.save(update_fields=["estado", "cita", "actualizada_en"])

    def resumen(self) -> dict:
        datos = SolicitudEspera.objects.aggregate(
            en_espera=Count("pk", filter=Q(estado=Estado.EN_ESPERA)),
            contactados=Count("pk", filter=Q(estado=Estado.CONTACTADO)),
            sin_contacto=Count("pk", filter=Q(estado=Estado.SIN_CONTACTO)),
            agendados=Count("pk", filter=Q(estado=Estado.AGENDADO)),
        )
        return datos

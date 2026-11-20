"""AsistenciaService: registra si el paciente asistió o no a su cita."""
from django.db.models import Q
from django.utils import timezone

from citas.models import Cita
from core import roles
from core.exceptions import ReglaNegocioError

from .models import Asistencia


class AsistenciaService:
    def citas_del_dia(self, fecha, policlinico=None, profesional=None, texto=""):
        qs = (Cita.objects.filter(cupo__fecha=fecha)
              .select_related("paciente", "cupo__agenda__profesional__especialidad", "cupo__agenda__policlinico",
                              "asistencia")
              .order_by("cupo__hora_inicio", "es_sobrecupo"))
        if policlinico:
            qs = qs.filter(cupo__agenda__policlinico=policlinico)
        if profesional:
            qs = qs.filter(cupo__agenda__profesional=profesional)
        texto = (texto or "").strip()
        if texto:
            qs = qs.filter(Q(paciente__nombre__icontains=texto) | Q(paciente__rut__icontains=texto.replace(".", "")))
        return qs

    @staticmethod
    def resumen(citas) -> dict:
        r = {"asistieron": 0, "no_asistieron": 0, "sin_registrar": 0}
        for c in citas:
            if c.estado == Cita.Estado.CANCELADA:
                continue
            a = c.asistencia_registrada
            if a is None:
                r["sin_registrar"] += 1
            elif a.asistio:
                r["asistieron"] += 1
            else:
                r["no_asistieron"] += 1
        return r

    def registrar(self, cita: Cita, asistio: bool, usuario) -> Asistencia:
        """Si se marcó mal, volver a registrar corrige el dato."""
        roles.exigir_rol(usuario, roles.TENS)
        roles.exigir_policlinico(usuario, cita.cupo.agenda.policlinico_id)
        if cita.estado == Cita.Estado.CANCELADA:
            raise ReglaNegocioError("La cita está cancelada: no se registra asistencia.", "ASISTENCIA")
        if cita.cupo.fecha > timezone.localdate():
            raise ReglaNegocioError("La asistencia se registra el día de la cita o después.", "ASISTENCIA")
        asistencia, _ = Asistencia.objects.update_or_create(
            cita=cita, defaults={"asistio": asistio, "registrada_por": usuario, "registrada_en": timezone.now()})
        return asistencia

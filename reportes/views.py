from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render

from core import roles
from profesionales.models import Policlinico, Profesional

from .services import PERIODOS, ReporteService, construir_filtros

servicio = ReporteService()


def _filtros(request):
    g = request.GET
    pol = Policlinico.objects.filter(pk=g.get("policlinico") or None).first()
    prof = Profesional.objects.filter(pk=g.get("profesional") or None).first()
    solo_propio = not roles.tiene_rol(request.user, roles.ADMINISTRACION)
    if solo_propio:  # rol Profesional: solo sus propias estadísticas
        prof = getattr(request.user, "profesional", None)
        if prof is None:
            raise PermissionDenied("Su usuario no está asociado a un profesional.")
    return construir_filtros(g.get("periodo", "3m"), pol, prof), solo_propio


@roles.rol_requerido(roles.ADMINISTRACION, roles.PROFESIONAL)
def inicio(request):
    f, solo_propio = _filtros(request)
    tab = request.GET.get("tab", "demanda" if solo_propio else "caracterizacion")
    ctx = {
        "f": f, "tab": tab, "solo_propio": solo_propio, "periodo": request.GET.get("periodo", "3m"),
        "periodos": [(k, t) for k, t, _ in PERIODOS],
        "policlinicos": Policlinico.objects.all(), "profesionales": Profesional.objects.all(),
        "qs": request.GET.urlencode(),
    }
    ctx["datos"] = servicio.demanda(f) if tab == "demanda" else servicio.caracterizacion(f)
    return render(request, "reportes/inicio.html", ctx)


@roles.rol_requerido(roles.ADMINISTRACION, roles.PROFESIONAL)
def csv_demanda(request):
    f, _ = _filtros(request)
    resp = HttpResponse(servicio.csv_demanda(f), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="demanda_{f.desde:%Y%m%d}_{f.hasta:%Y%m%d}.csv"'
    return resp

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from core import roles
from pacientes.models import Paciente

from .forms import FiltroPacientesForm, FiltroReporteForm
from .services import ReporteService, construir_filtros

servicio = ReporteService()
solo_admin = roles.rol_requerido(roles.ADMINISTRACION)

FILTROS_CITA = ("periodo", "desde", "hasta", "policlinico", "especialidad", "profesional", "estado", "asistencia",
                "canal", "sobrecupo")
TABS = [("caracterizacion", "Caracterización"), ("demanda", "Demanda y atención"), ("pacientes", "Pacientes")]


def _filtros(request, form_class=FiltroReporteForm, periodo="3m"):
    datos = request.GET.copy()
    datos.setdefault("periodo", periodo)
    form = form_class(datos)
    form.is_valid()  # si un filtro no es válido se ignora y se muestra su error; el resto se aplica
    return form, construir_filtros(form.cleaned_data)


def _qs_sin(request, *claves) -> str:
    q = request.GET.copy()
    for c in claves:
        q.pop(c, None)
    return q.urlencode()


def _csv(texto: str, nombre: str) -> HttpResponse:
    resp = HttpResponse(texto, content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return resp


@solo_admin
def inicio(request):
    tab = request.GET.get("tab") if request.GET.get("tab") in dict(TABS) else "caracterizacion"
    form, f = _filtros(request, FiltroPacientesForm if tab == "pacientes" else FiltroReporteForm)
    ctx = {"form": form, "f": f, "tab": tab, "tabs": TABS, "qs": _qs_sin(request, "tab", "page"),
           "qs_filtros": _qs_sin(request, "page")}
    if tab == "pacientes":
        # al abrir el historial se mantienen el período y los filtros de la cita
        hist = {k: v for k, v in request.GET.items() if k in FILTROS_CITA and v}
        hist.setdefault("periodo", "3m")
        ctx["qs_hist"] = urlencode(hist)
        qs = servicio.pacientes(f)
        ctx["resumen"] = servicio.resumen_pacientes(qs)
        ctx["pagina"] = Paginator(qs, 40).get_page(request.GET.get("page"))
    elif tab == "demanda":
        ctx["datos"] = servicio.demanda(f)
    else:
        ctx["datos"] = servicio.caracterizacion(f)
    return render(request, "reportes/inicio.html", ctx)


@solo_admin
def csv_demanda(request):
    _, f = _filtros(request)
    return _csv(servicio.csv_demanda(f), "demanda_y_atencion.csv")


@solo_admin
def csv_pacientes(request):
    _, f = _filtros(request, FiltroPacientesForm)
    return _csv(servicio.csv_pacientes(f), "pacientes.csv")


@solo_admin
def paciente(request, pk):
    p = get_object_or_404(Paciente.objects.select_related("adulto_responsable"), pk=pk)
    form, f = _filtros(request, periodo="todo")
    return render(request, "reportes/paciente.html", {
        "p": p, "form": form, "f": f, "datos": servicio.historial(p, f),
        "qs": request.GET.urlencode(), "volver": request.GET.get("volver", ""),
    })


@solo_admin
def csv_paciente(request, pk):
    p = get_object_or_404(Paciente, pk=pk)
    _, f = _filtros(request, periodo="todo")
    return _csv(servicio.csv_historial(p, f), f"historial_{p.rut}.csv")

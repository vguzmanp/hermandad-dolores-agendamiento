from datetime import timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from citas.models import Cita
from core import roles
from core.exceptions import ReglaNegocioError
from profesionales.models import Policlinico, Profesional

from .services import AsistenciaService

servicio = AsistenciaService()


@roles.rol_requerido(roles.TENS)
def lista(request):
    hoy = timezone.localdate()
    fecha = parse_date(request.GET.get("fecha") or "") or hoy
    pol = Policlinico.objects.filter(pk=request.GET.get("policlinico") or None).first()
    prof = Profesional.objects.filter(pk=request.GET.get("profesional") or None).first()
    q = request.GET.get("q", "")
    citas = list(servicio.citas_del_dia(fecha, pol, prof, q))
    return render(request, "asistencia/lista.html", {
        "fecha": fecha, "hoy": hoy, "anterior": fecha - timedelta(days=1), "siguiente": fecha + timedelta(days=1),
        "citas": citas, "resumen": servicio.resumen(citas), "futuro": fecha > hoy,
        "policlinicos": Policlinico.objects.filter(activo=True), "profesionales": Profesional.objects.filter(activo=True),
        "pol": pol, "prof": prof, "q": q,
    })


@roles.rol_requerido(roles.TENS)
@require_POST
def registrar(request, pk):
    cita = get_object_or_404(Cita, pk=pk)
    try:
        servicio.registrar(cita, request.POST.get("asistio") == "1", request.user)
    except ReglaNegocioError as e:
        messages.error(request, str(e))
    siguiente = request.POST.get("next")
    if siguiente and url_has_allowed_host_and_scheme(siguiente, {request.get_host()}):
        return redirect(siguiente)
    return redirect("asistencia:lista")

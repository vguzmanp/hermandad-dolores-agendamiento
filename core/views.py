from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from . import roles as r


def home(request):
    """Portada pública (¿Cómo quieres entrar?) o el inicio según el rol."""
    u = request.user
    if not u.is_authenticated:
        return render(request, "core/portada.html")
    if r.tiene_rol(u, r.TENS):
        return inicio_tens(request)
    if r.tiene_rol(u, r.ADMINISTRACION):
        return inicio_admin(request)
    return inicio_profesional(request)


def inicio_tens(request):
    from citas.services import ConfirmacionService, resumen_tens

    hoy = timezone.localdate()
    habil = proximo_dia_habil(hoy)
    dia = parse_date(request.GET.get("dia") or "") or habil
    citas = [c for c in ConfirmacionService().citas_del_dia(dia) if c.estado != "cancelada"]
    return render(request, "core/inicio_tens.html", {
        "hoy": hoy, "dia": dia, "dia_anterior": dia - timedelta(days=1), "dia_siguiente": dia + timedelta(days=1),
        "es_manana": dia == hoy + timedelta(days=1), "es_proximo_habil": dia == habil,
        "resumen": resumen_tens(hoy), "citas": citas,
    })


def proximo_dia_habil(d):
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def inicio_admin(request):
    from reportes.services import indicadores_admin

    return render(request, "core/inicio_admin.html", {"hoy": timezone.localdate(), "ind": indicadores_admin()})


def inicio_profesional(request):
    from citas.services import ConfirmacionService

    hoy = timezone.localdate()
    prof = getattr(request.user, "profesional", None)
    citas = []
    if prof:
        citas = [c for c in ConfirmacionService().citas_del_dia(hoy) if c.cupo.agenda.profesional_id == prof.pk]
    return render(request, "core/inicio_profesional.html", {"hoy": hoy, "profesional": prof, "citas": citas})

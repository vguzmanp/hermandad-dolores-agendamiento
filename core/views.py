from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from . import roles as r


def home(request):
    """Sin sesión: el login. Con sesión: el inicio según el rol."""
    u = request.user
    if not u.is_authenticated:
        return redirect("login")
    if r.tiene_rol(u, r.TENS) and not (u.is_superuser or r.tiene_rol(u, r.ADMINISTRACION)):
        return inicio_tens(request)
    if r.tiene_rol(u, r.ADMINISTRACION):
        return inicio_admin(request)
    raise PermissionDenied("Su usuario no tiene un rol asignado (Administración o TENS/TONS).")


def inicio_tens(request):
    from citas.services import ConfirmacionService, resumen_tens

    pol = r.policlinico_de(request.user)
    hoy = timezone.localdate()
    habil = proximo_dia_habil(hoy)
    dia = parse_date(request.GET.get("dia") or "") or habil
    citas = ConfirmacionService().citas_del_dia(dia).exclude(estado="cancelada")
    if pol:
        citas = citas.filter(cupo__agenda__policlinico=pol)
    return render(request, "core/inicio_tens.html", {
        "hoy": hoy, "dia": dia, "dia_anterior": dia - timedelta(days=1), "dia_siguiente": dia + timedelta(days=1),
        "es_manana": dia == hoy + timedelta(days=1), "es_proximo_habil": dia == habil,
        "resumen": resumen_tens(hoy, pol), "citas": list(citas), "policlinico": pol,
    })


def proximo_dia_habil(d):
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def inicio_admin(request):
    from reportes.services import indicadores_admin

    return render(request, "core/inicio_admin.html", {"hoy": timezone.localdate(), "ind": indicadores_admin()})

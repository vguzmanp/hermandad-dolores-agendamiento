from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core import roles
from core.exceptions import ReglaNegocioError
from profesionales.models import Especialidad, Policlinico

from .models import SolicitudEspera
from .services import ListaEsperaRepository, ListaEsperaService, posiciones

repo = ListaEsperaRepository()
servicio = ListaEsperaService(repo)


@roles.rol_requerido(roles.TENS, roles.ADMINISTRACION)
def lista(request):
    g = request.GET
    pol_tens = roles.policlinico_de(request.user)
    especialidades = pol_tens.especialidades if pol_tens else Especialidad.objects.filter(activa=True)
    esp = especialidades.filter(pk=g.get("especialidad") or None).first()
    pol = pol_tens or Policlinico.objects.filter(pk=g.get("policlinico") or None).first()
    estado = g.get("estado") if g.get("estado") in SolicitudEspera.Estado.values else None
    solicitudes = list(repo.listar(esp, pol, estado))
    activas = [s for s in solicitudes if s.activa]
    otras = [s for s in solicitudes if not s.activa]
    sel = None
    if g.get("sel", "").isdigit():
        sel = next((s for s in solicitudes if s.pk == int(g["sel"])), None)
    filtros = {"especialidad": esp.pk if esp else "", "estado": estado or ""}
    if not pol_tens:
        filtros["policlinico"] = pol.pk if pol else ""
    return render(request, "lista_espera/lista.html", {
        "filas": activas + otras, "posiciones": posiciones(solicitudes), "sel": sel,
        "resumen": servicio.resumen(pol), "especialidades": especialidades, "esp": esp,
        "policlinicos": Policlinico.objects.filter(activo=True), "pol": pol, "pol_tens": pol_tens,
        "estado": estado, "estados": SolicitudEspera.Estado.choices, "resultados": SolicitudEspera.Resultado.choices,
        "puede_gestionar": roles.tiene_rol(request.user, roles.TENS),
        "filtros_qs": urlencode({k: v for k, v in filtros.items() if v}),
    })


@roles.rol_requerido(roles.TENS)
@require_POST
def gestionar(request, pk):
    pol_tens = roles.policlinico_de(request.user)
    qs = SolicitudEspera.objects.filter(policlinico=pol_tens) if pol_tens else SolicitudEspera.objects.all()
    s = get_object_or_404(qs, pk=pk)
    try:
        if request.POST.get("accion") == "subir":
            if servicio.subir(s, request.user):
                messages.success(request, f"{s.paciente.nombre} subió un lugar en la lista", extra_tags="toast")
            else:
                messages.info(request, "El paciente ya está primero en su lista.")
        else:
            estado = request.POST.get("estado")
            resultado = request.POST.get("resultado_contacto")
            if estado not in SolicitudEspera.Estado.values or resultado not in SolicitudEspera.Resultado.values:
                raise ReglaNegocioError("Estado no válido.")
            servicio.actualizar_estado(s, estado, resultado, request.POST.get("nota", "").strip(), request.user)
            messages.success(request, "Estado guardado", extra_tags="toast")
    except (ReglaNegocioError, PermissionDenied) as e:
        messages.error(request, str(e))
    filtros = request.POST.get("filtros", "")
    return redirect(f"{reverse('lista_espera:lista')}?sel={pk}" + (f"&{filtros}" if filtros else ""))

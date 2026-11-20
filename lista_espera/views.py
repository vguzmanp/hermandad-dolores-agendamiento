from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core import roles
from core.exceptions import ReglaNegocioError
from profesionales.models import Especialidad

from .models import SolicitudEspera
from .services import ListaEsperaRepository, ListaEsperaService

repo = ListaEsperaRepository()
servicio = ListaEsperaService(repo)


@roles.rol_requerido(roles.TENS, roles.ADMINISTRACION)
def lista(request):
    esp = Especialidad.objects.filter(pk=request.GET.get("especialidad") or None).first()
    estado = request.GET.get("estado") if request.GET.get("estado") in SolicitudEspera.Estado.values else None
    solicitudes = list(repo.listar(esp, estado))
    activas = [s for s in solicitudes if s.activa]
    otras = [s for s in solicitudes if not s.activa]
    posiciones = {s.pk: i for i, s in enumerate(activas, 1)}
    sel = None
    if request.GET.get("sel", "").isdigit():
        sel = next((s for s in solicitudes if s.pk == int(request.GET["sel"])), None)
    return render(request, "lista_espera/lista.html", {
        "filas": activas + otras, "posiciones": posiciones, "sel": sel, "resumen": servicio.resumen(),
        "especialidades": Especialidad.objects.filter(activa=True), "esp": esp, "estado": estado,
        "estados": SolicitudEspera.Estado.choices, "resultados": SolicitudEspera.Resultado.choices,
        "puede_gestionar": roles.tiene_rol(request.user, roles.TENS),
        "filtros_qs": urlencode({k: v for k, v in {"especialidad": esp.pk if esp else "", "estado": estado or ""}.items() if v}),
    })


@roles.rol_requerido(roles.TENS)
@require_POST
def gestionar(request, pk):
    s = get_object_or_404(SolicitudEspera, pk=pk)
    try:
        if request.POST.get("accion") == "subir":
            if servicio.subir(s, request.user):
                messages.success(request, f"{s.paciente.nombre} subió un lugar en la lista", extra_tags="toast")
            else:
                messages.info(request, "El paciente ya está primero en la lista.")
        else:
            estado = request.POST.get("estado")
            resultado = request.POST.get("resultado_contacto")
            if estado not in SolicitudEspera.Estado.values or resultado not in SolicitudEspera.Resultado.values:
                raise ReglaNegocioError("Estado no válido.", "RN-06")
            servicio.actualizar_estado(s, estado, resultado, request.POST.get("nota", "").strip(), request.user)
            messages.success(request, "Estado guardado", extra_tags="toast")
    except ReglaNegocioError as e:
        messages.error(request, str(e))
    qs = request.POST.get("filtros", "")
    return redirect(f"{reverse('lista_espera:lista')}?sel={pk}" + (f"&{qs}" if qs else ""))

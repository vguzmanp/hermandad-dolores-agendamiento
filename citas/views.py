from datetime import timedelta
from itertools import groupby

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from agenda.models import Cupo
from agenda.repositories import CupoRepository
from core import roles
from core.exceptions import ReglaNegocioError
from pacientes.models import Paciente

from .forms import AgendarForm, DisponibilidadForm, FiltroCitasForm
from .models import Cita, MensajeEnviado
from .repositories import CitaRepositoryPostgres
from .services import AgendamientoService, ConfirmacionService

repo = CitaRepositoryPostgres()
agendamiento = AgendamientoService(repo)
confirmacion = ConfirmacionService(repo, agendamiento=agendamiento)

solo_tens = roles.rol_requerido(roles.TENS)


def _solo_profesional(usuario) -> bool:
    """Usuario con rol Profesional y sin rol TENS/Administración: solo ve sus propias citas."""
    return roles.tiene_rol(usuario, roles.PROFESIONAL) and not roles.tiene_rol(usuario, roles.TENS, roles.ADMINISTRACION)


# --------------------------------------------------------------- disponibilidad
@solo_tens
def disponibilidad(request):
    hoy = timezone.localdate()
    form = DisponibilidadForm(request.GET or None, initial={"desde": hoy, "hasta": hoy + timedelta(days=7)})
    libres, sobrecupo = [], []
    if not form.is_bound or form.is_valid():
        d = form.cleaned_data if form.is_bound else {}
        desde = d.get("desde") or hoy
        hasta = d.get("hasta") or desde + timedelta(days=7)
        resultado = agendamiento.disponibilidad(desde, hasta, d.get("especialidad"), d.get("profesional"),
                                                d.get("policlinico"))
        libres, sobrecupo = resultado["libres"], resultado["sobrecupo"]
    paciente = None
    pid = request.GET.get("paciente")
    if pid and pid.isdigit():
        paciente = Paciente.objects.filter(pk=pid).first()
    return render(request, "citas/disponibilidad.html", {
        "form": form,
        "libres_por_fecha": [(f, list(g)) for f, g in groupby(libres, key=lambda c: c.fecha)],
        "n_libres": len(libres),
        "sobrecupo": sobrecupo,
        "paciente": paciente,
    })


def _agendar(request, cupo_id: int, es_sobrecupo: bool):
    cupo = get_object_or_404(CupoRepository().base(), pk=cupo_id)
    max_ses = 1 if es_sobrecupo else agendamiento.max_sesiones(cupo)
    inicial = {}
    pid = request.GET.get("paciente")
    if pid and pid.isdigit():
        p = Paciente.objects.filter(pk=pid).first()
        if p:
            inicial["rut"] = p.rut
    form = AgendarForm(request.POST or None, initial=inicial, max_sesiones=max_ses, sobrecupo=es_sobrecupo)

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            if es_sobrecupo:
                res = agendamiento.agendar_sobrecupo(form.paciente, cupo, request.user, d["dias_aviso"], d["observaciones"])
            else:
                res = agendamiento.agendar(form.paciente, cupo, request.user, d.get("sesiones", 1),
                                           d["dias_aviso"], d["observaciones"])
        except ReglaNegocioError as e:
            messages.error(request, str(e))
        else:
            return _exito_agendamiento(request, res, form.paciente, es_sobrecupo)

    return render(request, "citas/agendar.html", {
        "cupo": cupo, "form": form, "es_sobrecupo": es_sobrecupo, "max_sesiones": max_ses,
    })


def _exito_agendamiento(request, res, paciente, es_sobrecupo):
    n = len(res.citas)
    tipo = "Sobrecupo agendado" if es_sobrecupo else ("Cita agendada" if n == 1 else f"{n} sesiones agendadas")
    messages.success(request, f"{tipo} para {paciente.nombre}. Se envió el mensaje de agendamiento (simulado).")
    for aviso in res.advertencias:
        messages.warning(request, aviso)
    return redirect("citas:detalle", pk=res.citas[0].pk)


@solo_tens
def agendar(request, cupo_id):
    return _agendar(request, cupo_id, es_sobrecupo=False)


@solo_tens
def sobrecupo(request, cupo_id):
    return _agendar(request, cupo_id, es_sobrecupo=True)


# ------------------------------------------------------------------ consultas
@roles.rol_requerido(roles.TENS, roles.ADMINISTRACION, roles.PROFESIONAL)
def lista(request):
    hoy = timezone.localdate()
    form = FiltroCitasForm(request.GET or None, initial={"desde": hoy, "hasta": hoy + timedelta(days=7)})
    filtros = {"fecha_desde": hoy, "fecha_hasta": hoy + timedelta(days=7)}
    if form.is_bound and form.is_valid():
        d = form.cleaned_data
        filtros = {"fecha_desde": d["desde"], "fecha_hasta": d["hasta"], "profesional": d["profesional"],
                   "policlinico": d["policlinico"], "estado": d["estado"] or None}
    propio = _solo_profesional(request.user)
    if propio:
        prof = getattr(request.user, "profesional", None)
        if prof is None:
            raise PermissionDenied("Su usuario no está asociado a un profesional.")
        filtros["profesional"] = prof
        form.fields.pop("profesional", None)
    pagina = Paginator(repo.listar(**filtros), 50).get_page(request.GET.get("page"))
    return render(request, "citas/lista.html", {"form": form, "pagina": pagina, "solo_lectura": not roles.tiene_rol(request.user, roles.TENS)})


@roles.rol_requerido(roles.TENS, roles.ADMINISTRACION, roles.PROFESIONAL)
def detalle(request, pk):
    try:
        cita = repo.obtener(pk)
    except Cita.DoesNotExist:
        raise Http404
    if _solo_profesional(request.user) and cita.cupo.agenda.profesional.usuario_id != request.user.pk:
        raise PermissionDenied("Solo puede ver sus propias citas.")
    sesiones = []
    if cita.grupo_sesiones:
        sesiones = repo.listar().filter(grupo_sesiones=cita.grupo_sesiones).order_by("numero_sesion")
    return render(request, "citas/detalle.html", {
        "cita": cita,
        "sesiones": sesiones,
        "otras_del_cupo": [c for c in repo.listar().filter(cupo=cita.cupo).exclude(pk=cita.pk)],
        "mensajes_cita": cita.mensajes.all(),
        "puede_operar": roles.tiene_rol(request.user, roles.TENS),
    })


# ------------------------------------------------------------------- acciones
ACCIONES = {
    "recordatorio": "Recordatorio enviado (simulado).",
    "confirmar": "El paciente CONFIRMÓ su asistencia.",
    "sin_respuesta": "Cita marcada como «sin respuesta». Ahora el cupo admite un sobrecupo (RN-07).",
    "cancelar": "Cita cancelada. El cupo quedó liberado.",
}


@solo_tens
@require_POST
def accion(request, pk, accion):
    if accion not in ACCIONES:
        raise Http404
    cita = get_object_or_404(repo.listar(), pk=pk)
    try:
        if accion == "recordatorio":
            confirmacion.enviar_recordatorio(cita, request.user)
        elif accion == "confirmar":
            confirmacion.registrar_confirmacion(cita, request.user)
        elif accion == "sin_respuesta":
            confirmacion.marcar_sin_respuesta(cita, request.user)
        elif accion == "cancelar":
            motivo = request.POST.get("motivo", "").strip() or "Cancelada por el paciente"
            cancelada = confirmacion.registrar_cancelacion(cita, request.user, motivo)
            if cancelada.sobrecupo_promovido:
                messages.info(request, f"El sobrecupo de {cancelada.sobrecupo_promovido.paciente.nombre} "
                                       f"pasó a ser la cita normal del cupo.")
    except ReglaNegocioError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, ACCIONES[accion])
    siguiente = request.POST.get("next")
    if siguiente and siguiente.startswith("/") and not siguiente.startswith("//"):
        return redirect(siguiente)
    return redirect("citas:detalle", pk=pk)


@solo_tens
def recordatorios(request):
    return render(request, "citas/recordatorios.html", {
        "pendientes": confirmacion.recordatorios_pendientes(),
        "esperando": confirmacion.esperando_respuesta(),
        "sin_respuesta": repo.listar(fecha_desde=timezone.localdate(), estado=Cita.Estado.SIN_RESPUESTA),
    })


@solo_tens
@require_POST
def enviar_todos(request):
    n = 0
    for cita in confirmacion.recordatorios_pendientes():
        confirmacion.enviar_recordatorio(cita, request.user)
        n += 1
    messages.success(request, f"Se enviaron {n} recordatorios (simulados).")
    return redirect("citas:recordatorios")


@solo_tens
def mensajes(request):
    qs = MensajeEnviado.objects.select_related("paciente", "cita__cupo", "enviado_por")
    pid = request.GET.get("paciente")
    if pid and pid.isdigit():
        qs = qs.filter(paciente_id=pid)
    pagina = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "citas/mensajes.html", {"pagina": pagina})

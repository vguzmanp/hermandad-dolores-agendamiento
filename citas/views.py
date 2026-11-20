import calendar
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from agenda.models import Cupo
from core import roles
from core.exceptions import ReglaNegocioError
from core.fechas import fecha_corta, mes_anio
from lista_espera.services import ListaEsperaService
from pacientes.models import Paciente
from pacientes.repositories import PacienteRepository
from profesionales.models import Especialidad, Policlinico, Profesional

from .forms import FiltroCitasForm
from .models import Cita, MensajeEnviado
from .repositories import CitaRepositoryPostgres
from .services import AgendamientoService, ConfirmacionService

repo = CitaRepositoryPostgres()
agendamiento = AgendamientoService(repo)
confirmacion = ConfirmacionService(repo, agendamiento=agendamiento)

solo_tens = roles.rol_requerido(roles.TENS)


def _toast(request, texto):
    messages.success(request, texto, extra_tags="toast")


def _volver(request, defecto):
    siguiente = request.POST.get("next") or request.GET.get("next")
    if siguiente and url_has_allowed_host_and_scheme(siguiente, {request.get_host()}):
        return redirect(siguiente)
    return redirect(defecto)


def _int(valor):
    return int(valor) if valor and str(valor).isdigit() else None


def _solo_profesional(usuario) -> bool:
    """Rol Profesional sin rol TENS/Administración: solo ve sus propias citas."""
    return roles.tiene_rol(usuario, roles.PROFESIONAL) and not roles.tiene_rol(usuario, roles.TENS, roles.ADMINISTRACION)


# ======================================================================
# Agendar nueva cita (TENS)
# ======================================================================
def _semanas_calendario(anio, mes, dias_disp, fecha_sel, hoy, url_dia):
    semanas = []
    for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(anio, mes):
        fila = []
        for d in semana:
            if d.month != mes:
                fila.append(None)
                continue
            n = dias_disp.get(d, 0)
            fila.append({"fecha": d, "disp": n > 0 and d >= hoy, "sel": d == fecha_sel, "hoy": d == hoy,
                         "url": url_dia(d) if n > 0 and d >= hoy else None})
        semanas.append(fila)
    return semanas


@solo_tens
def agendar(request):
    if request.method == "POST":
        return _agendar_post(request)
    g = request.GET
    hoy = timezone.localdate()

    reagendar = None
    if _int(g.get("reagendar")):
        reagendar = Cita.objects.select_related("cupo__agenda__profesional__especialidad", "paciente").filter(
            pk=g["reagendar"], estado__in=Cita.VIGENTES).first()
    paciente = reagendar.paciente if reagendar else Paciente.objects.filter(pk=_int(g.get("paciente"))).first()

    especialidades = Especialidad.objects.filter(activa=True)
    especialidad = especialidades.filter(pk=_int(g.get("especialidad"))).first()
    if especialidad is None and reagendar:
        especialidad = reagendar.cupo.agenda.profesional.especialidad
    policlinicos = Policlinico.objects.filter(activo=True)
    policlinico = policlinicos.filter(pk=_int(g.get("policlinico"))).first()

    profesionales = Profesional.objects.filter(activo=True).select_related("especialidad")
    if especialidad:
        profesionales = profesionales.filter(especialidad=especialidad)
    if policlinico:
        profesionales = profesionales.filter(agendas__policlinico=policlinico, agendas__activa=True).distinct()
    profesional = profesionales.filter(pk=_int(g.get("profesional"))).first()
    if profesional is None and reagendar and reagendar.cupo.agenda.profesional in profesionales:
        profesional = reagendar.cupo.agenda.profesional
    if profesional is None and especialidad:
        profesional = profesionales.first()

    canal = g.get("canal") or (reagendar.canal if reagendar else Cita.Canal.PRESENCIAL)
    max_ses = agendamiento.max_sesiones(profesional.especialidad) if profesional else 1
    sesiones = min(_int(g.get("sesiones")) or 1, max_ses)

    # Mes y días con horas disponibles
    try:
        anio, mes = (int(x) for x in g.get("mes", "").split("-"))
        date(anio, mes, 1)
    except ValueError:
        base = date.fromisoformat(g["fecha"]) if g.get("fecha") else hoy
        anio, mes = base.year, base.month
    primero = date(anio, mes, 1)
    ultimo = date(anio, mes, calendar.monthrange(anio, mes)[1])
    filtros = {"profesional": profesional, "policlinico": policlinico}
    dias_disp = agendamiento.dias_con_horas(max(primero, hoy), ultimo, **filtros) if profesional and ultimo >= hoy else {}
    try:
        fecha = date.fromisoformat(g["fecha"]) if g.get("fecha") else None
    except ValueError:
        fecha = None
    if fecha is None or fecha.month != mes:
        fecha = min(dias_disp) if dias_disp else None

    libres, sobrecupo = [], []
    if profesional and fecha:
        disp = agendamiento.disponibilidad(fecha, fecha, profesional=profesional, policlinico=policlinico)
        libres = disp["libres"]
        sobrecupo = [c for c in disp["sobrecupo"] if not paciente or c.cita_normal.paciente_id != paciente.pk]
    params = {k: v for k, v in {
        "paciente": paciente.pk if paciente else None, "especialidad": especialidad.pk if especialidad else None,
        "policlinico": policlinico.pk if policlinico else None, "profesional": profesional.pk if profesional else None,
        "canal": canal, "sesiones": sesiones if sesiones > 1 else None,
        "reagendar": reagendar.pk if reagendar else None, "espera": _int(g.get("espera")),
    }.items() if v}

    def url(**cambios):
        q = {**params, **cambios}
        return "?" + urlencode({k: v for k, v in q.items() if v not in (None, "")})

    mes_ant = (primero - timedelta(days=1)).replace(day=1)
    mes_sig = ultimo + timedelta(days=1)

    # Búsqueda de paciente
    q = g.get("q", "").strip()
    encontrados = PacienteRepository().buscar(q)[:8] if q and not paciente else []
    citas_paciente = []
    en_espera = None
    if paciente:
        citas_paciente = (repo.listar(paciente=paciente).select_related("asistencia")
                          .order_by("-cupo__fecha", "-cupo__hora_inicio")[:15])
        if especialidad:
            from lista_espera.models import SolicitudEspera
            en_espera = SolicitudEspera.objects.filter(paciente=paciente, especialidad=especialidad,
                                                       estado__in=SolicitudEspera.ACTIVOS).first()

    return render(request, "citas/agendar.html", {
        "hoy": hoy, "paciente": paciente, "reagendar": reagendar, "q": q, "encontrados": encontrados,
        "especialidades": especialidades, "especialidad": especialidad,
        "policlinicos": policlinicos, "policlinico": policlinico,
        "profesionales": profesionales, "profesional": profesional,
        "canales": Cita.Canal.choices, "canal": canal, "max_ses": max_ses, "sesiones": sesiones,
        "rango_sesiones": range(1, max_ses + 1),
        "titulo_mes": mes_anio(primero),
        "url_mes_ant": url(mes=mes_ant.strftime("%Y-%m")) if mes_ant >= hoy.replace(day=1) else None,
        "url_mes_sig": url(mes=mes_sig.strftime("%Y-%m")),
        "semanas": _semanas_calendario(anio, mes, dias_disp, fecha, hoy, lambda d: url(fecha=d.isoformat())),
        "fecha": fecha, "libres": libres, "sobrecupo": sobrecupo,
        "citas_paciente": citas_paciente, "en_espera": en_espera, "params": params,
        "url_cambiar_paciente": url(paciente=""),
    })


def _agendar_post(request):
    p = request.POST
    paciente = get_object_or_404(Paciente, pk=_int(p.get("paciente")))
    params = {k: p.get(k) for k in ("paciente", "especialidad", "policlinico", "profesional", "canal") if p.get(k)}
    volver = redirect(f"{request.path}?{urlencode(params)}")
    canal = p.get("canal") if p.get("canal") in Cita.Canal.values else Cita.Canal.PRESENCIAL

    if p.get("accion") == "espera":
        esp = get_object_or_404(Especialidad, pk=_int(p.get("especialidad")))
        prof = Profesional.objects.filter(pk=_int(p.get("profesional"))).first()
        pol = Policlinico.objects.filter(pk=_int(p.get("policlinico"))).first()
        ListaEsperaService().anotar(paciente, esp, prof, pol, canal, request.user)
        _toast(request, f"{paciente.nombre} quedó anotado/a en la lista de espera")
        return volver

    cupo = get_object_or_404(Cupo.objects.select_related("agenda__profesional__especialidad"), pk=_int(p.get("cupo")))
    es_sobrecupo = p.get("tipo") == "sobrecupo"
    try:
        if _int(p.get("reagendar")):
            original = get_object_or_404(Cita, pk=p["reagendar"], paciente=paciente)
            nueva = agendamiento.reagendar(original, cupo, request.user, es_sobrecupo=es_sobrecupo)
            _toast(request, f"Hora cambiada a {fecha_corta(nueva.cupo.fecha)} {nueva.cupo.hora_inicio:%H:%M}. La anterior quedó libre.")
            return volver
        if es_sobrecupo:
            res = agendamiento.agendar_sobrecupo(paciente, cupo, request.user, canal=canal)
        else:
            res = agendamiento.agendar(paciente, cupo, request.user, _int(p.get("sesiones")) or 1, canal=canal)
    except ReglaNegocioError as e:
        messages.error(request, str(e))
        return volver
    n = len(res.citas)
    texto = "Sobrecupo agendado" if es_sobrecupo else ("Cita agendada" if n == 1 else f"{n} sesiones agendadas")
    _toast(request, f"{texto} · aviso enviado por WhatsApp")
    for aviso in res.advertencias:
        messages.warning(request, aviso)
    return volver


# ======================================================================
# Listado, detalle y acciones
# ======================================================================
@roles.rol_requerido(roles.TENS, roles.ADMINISTRACION, roles.PROFESIONAL)
def lista(request):
    hoy = timezone.localdate()
    form = FiltroCitasForm(request.GET or None, initial={"desde": hoy, "hasta": hoy + timedelta(days=7)})
    filtros = {"fecha_desde": hoy, "fecha_hasta": hoy + timedelta(days=7)}
    if form.is_bound and form.is_valid():
        d = form.cleaned_data
        filtros = {"fecha_desde": d["desde"], "fecha_hasta": d["hasta"], "profesional": d["profesional"],
                   "policlinico": d["policlinico"], "estado": d["estado"] or None}
    if _solo_profesional(request.user):
        prof = getattr(request.user, "profesional", None)
        if prof is None:
            raise PermissionDenied("Su usuario no está asociado a un profesional.")
        filtros["profesional"] = prof
        form.fields.pop("profesional", None)
    qs = repo.listar(**filtros).select_related("asistencia").order_by("cupo__fecha", "cupo__hora_inicio")
    pagina = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(request, "citas/lista.html", {"form": form, "pagina": pagina,
                                                "solo_lectura": not roles.tiene_rol(request.user, roles.TENS)})


@roles.rol_requerido(roles.TENS, roles.ADMINISTRACION, roles.PROFESIONAL)
def detalle(request, pk):
    try:
        cita = repo.obtener(pk)
    except Cita.DoesNotExist:
        raise Http404
    if _solo_profesional(request.user) and cita.cupo.agenda.profesional.usuario_id != request.user.pk:
        raise PermissionDenied("Solo puede ver sus propias citas.")
    sesiones = repo.listar().filter(grupo_sesiones=cita.grupo_sesiones).order_by("numero_sesion") if cita.grupo_sesiones else []
    return render(request, "citas/detalle.html", {
        "cita": cita, "sesiones": sesiones,
        "otras_del_cupo": list(repo.listar().filter(cupo=cita.cupo).exclude(pk=cita.pk)),
        "mensajes_cita": cita.mensajes.all(),
        "puede_operar": roles.tiene_rol(request.user, roles.TENS),
    })


@solo_tens
@require_POST
def accion(request, pk, accion):
    cita = get_object_or_404(repo.listar(), pk=pk)
    try:
        if accion == "aviso":
            if confirmacion.enviar_recordatorio(cita, request.user):
                _toast(request, "Aviso enviado por WhatsApp")
            else:
                messages.error(request, f"No se pudo enviar el aviso por WhatsApp a {cita.paciente.nombre}: revise el "
                                        f"celular o llame al paciente y registre su respuesta.")
        elif accion == "respuesta":
            confirmacion.registrar_respuesta(cita, request.POST.get("respuesta", ""), request.user)
            _toast(request, "Respuesta registrada")
        elif accion == "confirmar":
            confirmacion.registrar_confirmacion(cita, request.user)
            _toast(request, "Cita confirmada")
        elif accion == "sin_respuesta":
            confirmacion.marcar_sin_respuesta(cita, request.user)
            _toast(request, "Cita marcada sin respuesta: admite un sobrecupo")
        elif accion == "cancelar":
            cancelada = confirmacion.registrar_cancelacion(cita, request.user, request.POST.get("motivo") or "Cancelada por la TENS")
            _toast(request, "Cita cancelada: la hora quedó libre")
            if getattr(cancelada, "sobrecupo_promovido", None):
                messages.info(request, f"El sobrecupo de {cancelada.sobrecupo_promovido.paciente.nombre} pasó a ser la cita del cupo.")
        else:
            raise Http404
    except ReglaNegocioError as e:
        messages.error(request, str(e))
    return _volver(request, "home")


@solo_tens
@require_POST
def enviar_todos(request):
    enviados, fallidos = confirmacion.enviar_pendientes(request.user)
    _toast(request, f"Avisos enviados: {enviados}" + (f" · con falla: {fallidos}" if fallidos else ""))
    return _volver(request, "home")


@solo_tens
def mensajes(request):
    qs = MensajeEnviado.objects.select_related("paciente", "cita__cupo", "enviado_por")
    pid = _int(request.GET.get("paciente"))
    if pid:
        qs = qs.filter(paciente_id=pid)
    canal = request.GET.get("canal")
    if canal in MensajeEnviado.Canal.values:
        qs = qs.filter(canal=canal)
    pagina = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "citas/mensajes.html", {"pagina": pagina, "canal": canal})


def redirigir_agendar(request, *args, **kwargs):
    return redirect("citas:agendar")

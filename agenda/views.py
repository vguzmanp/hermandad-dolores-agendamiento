"""Horario semanal (bloques) y calendario para bloquear / liberar horas."""
from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from core import roles
from core.exceptions import ReglaNegocioError
from core.fechas import DIAS_CORTOS, lunes_de, rango_semana
from profesionales.models import Especialidad, Profesional

from .forms import BloqueSemanalForm
from .models import Agenda, Cupo
from .services import AgendaService

servicio = AgendaService()
tens_o_admin = roles.rol_requerido(roles.TENS, roles.ADMINISTRACION)


def _seleccion(request):
    """Especialidad y profesional elegidos en los filtros (por defecto, el primero)."""
    datos = request.GET if request.method == "GET" else request.POST
    pol_tens = roles.policlinico_de(request.user)
    especialidades = pol_tens.especialidades if pol_tens else Especialidad.objects.filter(activa=True)
    esp = especialidades.filter(pk=datos.get("especialidad") or None).first()
    profesionales = Profesional.objects.select_related("especialidad")
    if not roles.tiene_rol(request.user, roles.ADMINISTRACION):
        profesionales = profesionales.filter(activo=True)
    if pol_tens:  # la TENS/TONS solo ve a quienes atienden en su policlínico
        profesionales = profesionales.filter(agendas__policlinico=pol_tens, agendas__activa=True).distinct()
    prof = profesionales.filter(pk=datos.get("profesional") or None).first()
    if prof and esp is None:
        esp = prof.especialidad
    if esp:
        profesionales = profesionales.filter(especialidad=esp)
    if prof is None or (esp and prof.especialidad_id != esp.pk):
        prof = profesionales.first()
    return especialidades, esp, profesionales, prof


def _tabs(request, prof):
    q = f"?profesional={prof.pk}" if prof else ""
    tabs = []
    if roles.tiene_rol(request.user, roles.ADMINISTRACION):
        tabs.append(("Equipo", reverse("profesionales:lista"), "equipo"))
    tabs.append(("Calendario" if not roles.tiene_rol(request.user, roles.ADMINISTRACION) else "Bloquear y liberar horas",
                 reverse("agenda:calendario") + q, "calendario"))
    tabs.append(("Horario semanal", reverse("agenda:horario") + q, "horario"))
    return tabs


# --------------------------------------------------------------- horario
@tens_o_admin
def horario(request):
    especialidades, esp, profesionales, prof = _seleccion(request)
    es_admin = roles.tiene_rol(request.user, roles.ADMINISTRACION)
    form = BloqueSemanalForm(request.POST or None) if es_admin else None
    abrir_modal = False
    if request.method == "POST":
        if not es_admin or prof is None:
            return redirect("agenda:horario")
        if form.is_valid():
            d = form.cleaned_data
            agenda = Agenda(profesional=prof, policlinico=d["policlinico"], dia_semana=d["dia_semana"],
                            hora_inicio=d["hora_inicio"], hora_fin=d["hora_fin"], vigente_desde=timezone.localdate())
            try:
                _, n = servicio.agregar_bloque(agenda, request.user)
            except ReglaNegocioError as e:
                form.add_error(None, f"{e.mensaje} No se guardó.")
                abrir_modal = True
            else:
                messages.success(request, f"Bloque agregado · {n} cupos generados", extra_tags="toast")
                return redirect(f"{reverse('agenda:horario')}?profesional={prof.pk}")
        else:
            abrir_modal = True
    bloques = prof.agendas.filter(activa=True).select_related("policlinico").order_by("dia_semana", "hora_inicio") if prof else []
    pol_tens = roles.policlinico_de(request.user)
    if prof and pol_tens:
        bloques = bloques.filter(policlinico=pol_tens)
    return render(request, "agenda/horario.html", {
        "especialidades": especialidades, "esp": esp, "profesionales": profesionales, "prof": prof,
        "bloques": bloques, "form": form, "abrir_modal": abrir_modal, "es_admin_agenda": es_admin,
        "tabs": _tabs(request, prof), "tab": "horario",
    })


@roles.rol_requerido(roles.ADMINISTRACION)
@require_POST
def quitar_bloque(request, pk):
    agenda = get_object_or_404(Agenda, pk=pk)
    servicio.quitar_bloque(agenda, request.user)
    messages.success(request, "Bloque quitado del horario semanal", extra_tags="toast")
    return redirect(f"{reverse('agenda:horario')}?profesional={agenda.profesional_id}")


# ------------------------------------------------------------ calendario
@tens_o_admin
def calendario(request):
    especialidades, esp, profesionales, prof = _seleccion(request)
    hoy = timezone.localdate()
    lunes = lunes_de(parse_date(request.GET.get("semana") or "") or hoy)
    semanas = [lunes_de(hoy) + timedelta(weeks=i) for i in range(-2, 9)]
    if lunes not in semanas:
        semanas.append(lunes)
        semanas.sort()
    dias = [lunes + timedelta(days=i) for i in range(7)]
    cupos = []
    pol_tens = roles.policlinico_de(request.user)
    if prof:
        qs = Cupo.objects.filter(agenda__profesional=prof, fecha__range=(dias[0], dias[-1]))
        if pol_tens:
            qs = qs.filter(agenda__policlinico=pol_tens)
        cupos = list(qs.select_related("agenda__policlinico").prefetch_related("citas"))
    if not any(c.fecha.weekday() >= 5 for c in cupos):
        dias = dias[:5]
    horas = sorted({c.hora_inicio for c in cupos})
    por_celda = {(c.fecha, c.hora_inicio): c for c in cupos}
    filas = []
    for h in horas:
        celdas = []
        for d in dias:
            c = por_celda.get((d, h))
            estado = None
            if c:
                estado = "bloqueado" if c.bloqueado else ("con_cita" if c.citas_vigentes else "disponible")
            celdas.append({"cupo": c, "estado": estado, "pasado": d < hoy})
        filas.append({"hora": h, "celdas": celdas})
    return render(request, "agenda/calendario.html", {
        "especialidades": especialidades, "esp": esp, "profesionales": profesionales, "prof": prof,
        "semanas": [(s, rango_semana(s)) for s in semanas], "lunes": lunes,
        "dias": [(d, f"{DIAS_CORTOS[d.weekday()]} {d.day}") for d in dias], "filas": filas,
        "tabs": _tabs(request, prof), "tab": "calendario", "n_columnas": len(dias),
    })


@tens_o_admin
@require_POST
def calendario_accion(request):
    ids = [int(x) for x in request.POST.getlist("cupo") if x.isdigit()]
    qs = Cupo.objects.filter(pk__in=ids, fecha__gte=timezone.localdate())
    pol_tens = roles.policlinico_de(request.user)
    if pol_tens:
        qs = qs.filter(agenda__policlinico=pol_tens)
    cupos = list(qs.select_related("agenda").prefetch_related("citas"))
    accion = request.POST.get("accion")
    if not cupos:
        messages.error(request, "Selecciona uno o más bloques.")
    elif accion == "bloquear":
        b, o = servicio.bloquear_varios(cupos, request.POST.get("motivo", "").strip(), request.user)
        messages.success(request, f"{b} hora{'s' if b != 1 else ''} bloqueada{'s' if b != 1 else ''}", extra_tags="toast")
        if o:
            messages.warning(request, f"{o} bloque(s) con cita no se bloquearon: la cita sigue ocupando la hora.")
    elif accion == "liberar":
        maximo = int(request.POST.get("de_a_poco") or 0) or None
        n = servicio.liberar_varios(cupos, request.user, maximo)
        messages.success(request, f"{n} hora{'s' if n != 1 else ''} liberada{'s' if n != 1 else ''}: vuelven a estar disponibles", extra_tags="toast")
    params = {k: request.POST.get(k) for k in ("especialidad", "profesional", "semana") if request.POST.get(k)}
    return redirect(f"{reverse('agenda:calendario')}?{urlencode(params)}")

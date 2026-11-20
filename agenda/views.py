from datetime import timedelta
from itertools import groupby

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core import roles
from core.exceptions import ReglaNegocioError
from profesionales.models import Policlinico, Profesional

from .forms import AgendaForm, BloquearDiaForm, GenerarCuposForm
from .models import Agenda, Cupo
from .repositories import AgendaRepository, CupoRepository
from .services import AgendaService

agendas_repo = AgendaRepository()
cupos_repo = CupoRepository()
servicio = AgendaService(agendas_repo, cupos_repo)

solo_admin = roles.rol_requerido(roles.ADMINISTRACION)


@solo_admin
def lista(request):
    prof = request.GET.get("profesional") or None
    pol = request.GET.get("policlinico") or None
    hoy = timezone.localdate()
    agendas = agendas_repo.listar(prof, pol).annotate(
        cupos_futuros=Count("cupos", filter=Q(cupos__fecha__gte=hoy)),
    )
    return render(request, "agenda/lista.html", {
        "agendas": agendas,
        "profesionales": Profesional.objects.filter(activo=True),
        "policlinicos": Policlinico.objects.all(),
        "prof_sel": prof, "pol_sel": pol,
    })


@solo_admin
def agenda_form(request, pk=None):
    instancia = get_object_or_404(Agenda, pk=pk) if pk else None
    form = AgendaForm(request.POST or None, instance=instancia)
    if request.method == "POST" and form.is_valid():
        try:
            agenda = servicio.guardar_agenda(form.save(commit=False), request.user)
        except ReglaNegocioError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, "Agenda guardada.")
            semanas = form.cleaned_data.get("generar_semanas") or 0
            if semanas and agenda.activa:
                hoy = timezone.localdate()
                n = servicio.generar_cupos(agenda, hoy, hoy + timedelta(weeks=semanas), request.user)
                messages.info(request, f"Se generaron {n} cupos nuevos.")
            return redirect("agenda:detalle", pk=agenda.pk)
    return render(request, "agenda/form.html", {"form": form, "agenda": instancia})


@solo_admin
def detalle(request, pk):
    agenda = get_object_or_404(agendas_repo.listar(), pk=pk)
    hoy = timezone.localdate()
    desde = parse_date(request.GET.get("desde") or "") or hoy
    hasta = parse_date(request.GET.get("hasta") or "") or desde + timedelta(weeks=3)
    cupos = list(cupos_repo.de_agenda(agenda, desde, hasta))
    por_fecha = [(f, list(g)) for f, g in groupby(cupos, key=lambda c: c.fecha)]
    return render(request, "agenda/detalle.html", {
        "agenda": agenda, "por_fecha": por_fecha, "desde": desde, "hasta": hasta,
        "form_generar": GenerarCuposForm(), "form_bloquear_dia": BloquearDiaForm(initial={"fecha": desde}),
    })


def _volver(request, agenda_id):
    siguiente = request.POST.get("next")
    if siguiente and url_has_allowed_host_and_scheme(siguiente, {request.get_host()}):
        return redirect(siguiente)
    return redirect("agenda:detalle", pk=agenda_id)


@solo_admin
@require_POST
def generar(request, pk):
    agenda = get_object_or_404(Agenda, pk=pk)
    form = GenerarCuposForm(request.POST)
    if form.is_valid():
        try:
            n = servicio.generar_cupos(agenda, form.cleaned_data["desde"], form.cleaned_data["hasta"], request.user)
            messages.success(request, f"Se generaron {n} cupos nuevos (los existentes no se duplican).")
        except ReglaNegocioError as e:
            messages.error(request, str(e))
    else:
        messages.error(request, " ".join(form.non_field_errors()) or "Revise las fechas.")
    return _volver(request, pk)


@solo_admin
@require_POST
def bloquear_cupo(request, pk):
    cupo = get_object_or_404(Cupo, pk=pk)
    try:
        servicio.bloquear_cupo(cupo, request.POST.get("motivo", "").strip(), request.user)
        messages.success(request, f"Cupo {cupo.fecha:%d/%m} {cupo.hora_inicio:%H:%M} bloqueado.")
    except ReglaNegocioError as e:
        messages.error(request, str(e))
    return _volver(request, cupo.agenda_id)


@solo_admin
@require_POST
def liberar_cupo(request, pk):
    cupo = get_object_or_404(Cupo, pk=pk)
    servicio.liberar_cupo(cupo, request.user)
    messages.success(request, f"Cupo {cupo.fecha:%d/%m} {cupo.hora_inicio:%H:%M} liberado.")
    return _volver(request, cupo.agenda_id)


@solo_admin
@require_POST
def bloquear_dia(request, pk):
    agenda = get_object_or_404(Agenda, pk=pk)
    form = BloquearDiaForm(request.POST)
    if form.is_valid():
        b, o = servicio.bloquear_dia(agenda, form.cleaned_data["fecha"], form.cleaned_data["motivo"], request.user)
        messages.success(request, f"{b} cupos bloqueados.")
        if o:
            messages.warning(request, f"{o} cupos no se bloquearon porque tienen citas vigentes.")
    else:
        messages.error(request, "Indique una fecha válida.")
    return _volver(request, pk)

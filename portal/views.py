"""
Portal público del paciente (sin cuenta ni clave).

Reserva en 4 pasos: 1) especialidad y policlínico (solo los que atienden esa
especialidad), 2) profesional y hora, 3) datos del paciente (por RUT: si ya
existe no se vuelven a pedir), 4) confirmar. Si no hay horas, el paciente puede
anotarse en la lista de espera de esa especialidad en ese policlínico.

El link del aviso (/c/<código>/) permite confirmar, cambiar o cancelar la hora.
"""
from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from agenda.models import Cupo
from citas import notificaciones as avisos
from citas.models import Cita
from citas.repositories import CitaRepositoryPostgres
from citas.services import AgendamientoService, ConfirmacionService
from core.exceptions import ReglaNegocioError
from core.fechas import DIAS_CORTOS, MESES_CORTOS
from lista_espera.services import ListaEsperaService
from pacientes.forms import AdultoResponsableForm, BuscarRutForm, PacienteForm
from pacientes.models import DocumentoPaciente, Paciente
from pacientes.services import DocumentoService, PacienteService
from profesionales.models import Especialidad, Policlinico, Profesional

repo = CitaRepositoryPostgres()
agendamiento = AgendamientoService(repo)
confirmacion = ConfirmacionService(repo, agendamiento=agendamiento)

DIAS_A_MOSTRAR = 6
DIAS_BUSQUEDA = 21


def _reserva(request) -> dict:
    return request.session.setdefault("reserva", {})


def _guardar(request, **datos):
    r = _reserva(request)
    r.update(datos)
    request.session.modified = True


def _chip(d):
    return f"{DIAS_CORTOS[d.weekday()]} {d.day} {MESES_CORTOS[d.month - 1]}"


# ----------------------------------------------------------- paso 1
def _especialidades_con_policlinicos():
    """Especialidades con al menos un policlínico donde se atienden, y esos policlínicos."""
    res = []
    for e in Especialidad.objects.filter(activa=True).order_by("nombre"):
        pols = list(e.policlinicos)
        if pols:
            res.append((e, pols))
    return res


def inicio(request):
    request.session.pop("reserva", None)
    opciones = _especialidades_con_policlinicos()
    policlinicos = {p.pk: p for _, pols in opciones for p in pols}
    return render(request, "portal/paso1.html", {
        "especialidades": [{"e": e, "pols": ",".join(str(p.pk) for p in pols)} for e, pols in opciones],
        "policlinicos": sorted(policlinicos.values(), key=lambda p: (p.es_telemedicina, p.nombre)),
        "esp_sel": request.GET.get("esp", ""), "pol_sel": request.GET.get("pol", ""),
    })


# ----------------------------------------------------------- paso 2
def _filtros_paso2(request):
    g = request.GET if request.method == "GET" else request.POST
    esp = Especialidad.objects.filter(pk=g.get("esp") or None, activa=True).first()
    pol = Policlinico.objects.filter(pk=g.get("pol") or None, activo=True).first()
    prof = Profesional.objects.filter(pk=g.get("prof") or None, activo=True).first()
    return esp, pol, prof


def horas(request):
    esp, pol, prof = _filtros_paso2(request)
    if esp is None:
        messages.error(request, "Elige una especialidad.")
        return redirect("portal:inicio")
    if pol is None or not esp.policlinicos.filter(pk=pol.pk).exists():
        messages.error(request, f"Elige un policlínico donde se atienda {esp.nombre}.")
        return redirect(f"{reverse('portal:inicio')}?esp={esp.pk}")
    if request.method == "POST":
        if request.POST.get("accion") == "espera":
            _guardar(request, esp=esp.pk, pol=pol.pk, prof=None, espera=True, cupo=None)
            return redirect("portal:datos")
        cupo = Cupo.objects.filter(pk=request.POST.get("cupo") or None).first()
        if cupo is None:
            messages.error(request, "Elige una hora.")
        else:
            _guardar(request, esp=esp.pk, pol=pol.pk if pol else None, prof=prof.pk if prof else None,
                     cupo=cupo.pk, espera=False)
            return redirect("portal:datos")

    hoy = timezone.localdate()
    hasta = hoy + timedelta(days=DIAS_BUSQUEDA)
    profesionales = Profesional.objects.filter(especialidad=esp, activo=True)
    if prof:
        profesionales = profesionales.filter(pk=prof.pk)
    if pol:
        profesionales = profesionales.filter(agendas__policlinico=pol, agendas__activa=True).distinct()
    base = {"esp": esp.pk, "pol": pol.pk if pol else "", "prof": prof.pk if prof else ""}
    base = {k: v for k, v in base.items() if v}
    seleccion = {k: v for k, v in request.GET.items() if k.startswith("d")}
    cupo_sel = Cupo.objects.select_related("agenda__profesional", "agenda__policlinico").filter(
        pk=request.GET.get("cupo") or None).first()
    tarjetas, total_libres = [], 0
    for p in profesionales:
        filtros = {"desde": hoy, "hasta": hasta, "profesional": p, "policlinico": pol}
        libres = list(repo.cupos_libres(filtros))
        total_libres += len(libres)
        # días con atención del profesional (aunque estén llenos), para mostrar «Sin horas»
        dias_agenda = sorted(set(Cupo.objects.filter(
            agenda__profesional=p, agenda__activa=True, fecha__range=(hoy, hasta),
            **({"agenda__policlinico": pol} if pol else {})).values_list("fecha", flat=True)))[:DIAS_A_MOSTRAR]
        por_dia = {}
        for c in libres:
            por_dia.setdefault(c.fecha, []).append(c)
        dia_sel = seleccion.get(f"d{p.pk}")
        dia_sel = next((d for d in dias_agenda if d.isoformat() == dia_sel), None)
        if dia_sel is None:
            dia_sel = next((d for d in dias_agenda if por_dia.get(d)), dias_agenda[0] if dias_agenda else None)

        def url(**cambios):
            q = {**base, **seleccion, **cambios}
            return "?" + urlencode({k: v for k, v in q.items() if v})

        tarjetas.append({
            "p": p,
            "dias": [{"fecha": d, "texto": _chip(d), "n": len(por_dia.get(d, [])), "activo": d == dia_sel,
                      "url": url(**{f"d{p.pk}": d.isoformat(), "cupo": ""})} for d in dias_agenda],
            "horas": [{"c": c, "url": url(**{f"d{p.pk}": dia_sel.isoformat(), "cupo": c.pk}),
                       "activo": cupo_sel and c.pk == cupo_sel.pk} for c in por_dia.get(dia_sel, [])],
        })
    return render(request, "portal/paso2.html", {
        "esp": esp, "pol": pol, "prof": prof, "tarjetas": tarjetas, "total_libres": total_libres,
        "cupo_sel": cupo_sel, "texto_sel": _chip(cupo_sel.fecha) if cupo_sel else "", "base": base,
    })


# ----------------------------------------------------------- paso 3
def datos(request):
    r = _reserva(request)
    if not r.get("cupo") and not r.get("espera"):
        return redirect("portal:inicio")
    familiar = (request.POST.get("quien") or request.GET.get("quien")) == "familiar"
    form_rut = BuscarRutForm(request.POST if request.POST.get("paso") == "rut" else None)
    nuevo = False
    form = form_resp = None

    if request.method == "POST" and request.POST.get("paso") == "rut" and form_rut.is_valid():
        rut = form_rut.cleaned_data["rut"]
        paciente = PacienteService().buscar_por_rut(rut)
        if paciente:
            return _paciente_listo(request, paciente)
        nuevo = True
        form = PacienteForm(initial={"rut": rut, "requiere_responsable": familiar})
        form_resp = AdultoResponsableForm()
    elif request.method == "POST" and request.POST.get("paso") == "registro":
        nuevo = True
        form = PacienteForm(request.POST)
        form_resp = AdultoResponsableForm(request.POST)
        form_rut = BuscarRutForm(initial={"rut": request.POST.get("rut")})
        if form.is_valid():
            paciente = form.save(commit=False)
            if not paciente.necesita_responsable or form_resp.is_valid():
                try:
                    paciente = PacienteService().registrar_web(
                        paciente, form_resp.save(commit=False) if paciente.necesita_responsable else None)
                except ReglaNegocioError as e:
                    messages.error(request, e.mensaje)
                else:
                    return _paciente_listo(request, paciente)
    if form is not None:
        form.fields["rut"].widget.attrs["readonly"] = True
        form.fields["correo"].label = "Correo electrónico (opcional, para recibir la confirmación)"
        form.fields["correo"].help_text = ""
    return render(request, "portal/paso3.html", {
        "form_rut": form_rut, "form": form, "form_resp": form_resp, "nuevo": nuevo, "familiar": familiar,
        "espera": r.get("espera"), "volver": _url_volver_paso2(r),
    })


def _url_volver_paso2(r):
    q = {k: r.get(k) for k in ("esp", "pol", "prof") if r.get(k)}
    return f"{reverse('portal:horas')}?{urlencode(q)}"


def _paciente_listo(request, paciente):
    r = _reserva(request)
    if r.get("espera"):
        esp = get_object_or_404(Especialidad, pk=r["esp"])
        pol = get_object_or_404(Policlinico, pk=r.get("pol"))
        try:
            ListaEsperaService().anotar(paciente, esp, pol, canal="web")
        except ReglaNegocioError as e:
            messages.error(request, e.mensaje)
            return redirect("portal:inicio")
        request.session.pop("reserva", None)
        request.session["espera_especialidad"] = f"{esp.nombre} · {pol.nombre}"
        return redirect("portal:espera_ok")
    _guardar(request, paciente=paciente.pk)
    return redirect("portal:confirmar")


# ----------------------------------------------------------- paso 4
def confirmar(request):
    r = _reserva(request)
    if not r.get("cupo") or not r.get("paciente"):
        return redirect("portal:inicio")
    cupo = get_object_or_404(Cupo.objects.select_related("agenda__profesional__especialidad", "agenda__policlinico"),
                             pk=r["cupo"])
    paciente = get_object_or_404(Paciente, pk=r["paciente"])
    if request.method == "POST":
        try:
            res = agendamiento.agendar_web(paciente, cupo)
        except ReglaNegocioError as e:
            messages.error(request, f"{e.mensaje} Elige otra hora.")
            return redirect(_url_volver_paso2(r))
        request.session.pop("reserva", None)
        return redirect("portal:listo", token=res.citas[0].token)
    return render(request, "portal/paso4.html", {"cupo": cupo, "paciente": paciente, "volver": _url_volver_paso2(r)})


def _cita(token):
    return get_object_or_404(Cita.objects.select_related(
        "paciente", "paciente__adulto_responsable", "cupo__agenda__profesional__especialidad", "cupo__agenda__policlinico"),
        token=token.upper())


def listo(request, token):
    cita = _cita(token)
    if request.method == "POST":
        servicio = DocumentoService()
        subidos = 0
        for campo, tipo in (("fonasa", DocumentoPaciente.Tipo.FONASA), ("cesfam", DocumentoPaciente.Tipo.CESFAM)):
            archivo = request.FILES.get(campo)
            if archivo:
                try:
                    servicio.adjuntar(cita.paciente, tipo, archivo)
                    subidos += 1
                except ReglaNegocioError as e:
                    messages.error(request, e.mensaje)
        if subidos:
            messages.success(request, "Documentos recibidos. ¡Gracias!")
        return redirect("portal:listo", token=cita.token)
    return render(request, "portal/listo.html", {"cita": cita})


def espera_ok(request):
    return render(request, "portal/espera_ok.html", {"especialidad": request.session.get("espera_especialidad", "")})


# ----------------------------------------------------- aviso y respuesta
def aviso(request, token):
    """Muestra el aviso tal como llegaría por WhatsApp y por correo (simulado)."""
    cita = _cita(token)
    a = avisos.aviso_recordatorio(cita)
    return render(request, "portal/aviso.html", {"cita": cita, "aviso": a, "link": avisos.link_cita(cita)})


def responder(request, token):
    cita = _cita(token)
    return render(request, "portal/responder.html", {"cita": cita})


@require_POST
def responder_accion(request, token, accion):
    cita = _cita(token)
    try:
        if accion == "confirmar":
            confirmacion.registrar_confirmacion(cita, por_paciente=True)
            return redirect(f"{reverse('portal:resultado', args=[cita.token])}?r=confirmada")
        if accion == "cancelar":
            confirmacion.registrar_cancelacion(cita, motivo="Cancelada por el paciente (link del aviso)", por_paciente=True)
            return redirect(f"{reverse('portal:resultado', args=[cita.token])}?r=cancelada")
    except ReglaNegocioError as e:
        messages.error(request, e.mensaje)
        return redirect("portal:responder", token=cita.token)
    raise Http404


def cambiar(request, token):
    cita = _cita(token)
    if not cita.es_vigente:
        messages.error(request, "Esta hora ya no se puede cambiar.")
        return redirect("portal:responder", token=cita.token)
    prof = cita.cupo.agenda.profesional
    if request.method == "POST":
        nuevo = Cupo.objects.filter(pk=request.POST.get("cupo") or None).first()
        if nuevo is None:
            messages.error(request, "Elige la nueva hora.")
        else:
            try:
                nueva = agendamiento.reagendar(cita, nuevo, por_paciente=True)
            except ReglaNegocioError as e:
                messages.error(request, e.mensaje)
            else:
                return redirect(f"{reverse('portal:resultado', args=[nueva.token])}?r=cambiada")
    hoy = timezone.localdate()
    libres = [c for c in repo.cupos_libres({"desde": hoy, "hasta": hoy + timedelta(days=DIAS_BUSQUEDA), "profesional": prof,
                                       "policlinico": cita.cupo.agenda.policlinico})
              if c.pk != cita.cupo_id]
    por_dia = {}
    for c in libres:
        por_dia.setdefault(c.fecha, []).append(c)
    dias = sorted(por_dia)[:DIAS_A_MOSTRAR]
    sel = request.GET.get("dia")
    dia_sel = next((d for d in dias if d.isoformat() == sel), dias[0] if dias else None)
    return render(request, "portal/cambiar.html", {
        "cita": cita, "prof": prof,
        "dias": [{"fecha": d, "texto": f"{DIAS_CORTOS[d.weekday()]} {d.day}", "n": len(por_dia[d]), "activo": d == dia_sel}
                 for d in dias],
        "horas": por_dia.get(dia_sel, []), "dia_sel": dia_sel,
        "texto_dia": f"{DIAS_CORTOS[dia_sel.weekday()]} {dia_sel.day}" if dia_sel else "",
    })


def resultado(request, token):
    cita = _cita(token)
    tipo = request.GET.get("r")
    if tipo not in ("confirmada", "cancelada", "cambiada"):
        return redirect("portal:responder", token=cita.token)
    return render(request, "portal/resultado.html", {"cita": cita, "tipo": tipo})

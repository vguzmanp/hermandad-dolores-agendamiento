from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core import roles

from .forms import EspecialidadForm, PoliclinicoForm, ProfesionalForm
from .models import Especialidad, Policlinico, Profesional
from .repositories import ProfesionalRepository
from .services import ProfesionalService

repo = ProfesionalRepository()
servicio = ProfesionalService(repo)

solo_admin = roles.rol_requerido(roles.ADMINISTRACION)


@solo_admin
def lista(request):
    """Pestaña «Equipo»: profesionales, horas por semana, citas futuras y estado."""
    hoy = timezone.localdate()
    editar = Profesional.objects.filter(pk=request.GET.get("editar") or request.POST.get("pk") or None).first()
    form = ProfesionalForm(request.POST or None, instance=editar)
    abrir_modal = bool(request.GET.get("nuevo") or editar and request.method == "GET")
    if request.method == "POST":
        if form.is_valid():
            prof = servicio.guardar(form.save(commit=False), request.user)
            if editar:
                messages.success(request, f"{prof.nombre} actualizado", extra_tags="toast")
                return redirect("profesionales:lista")
            messages.success(request, f"{prof.nombre} agregado: ahora define su horario semanal", extra_tags="toast")
            return redirect(f"{reverse('agenda:horario')}?profesional={prof.pk}")
        abrir_modal = True
    profesionales = (Profesional.objects.select_related("especialidad")
                     .prefetch_related("agendas__policlinico")
                     .annotate(citas_futuras=Count("agendas__cupos__citas", filter=Q(
                         agendas__cupos__fecha__gte=hoy,
                         agendas__cupos__citas__estado__in=["agendada", "confirmada", "sin_respuesta"]))))
    filas = []
    for p in profesionales:
        activas = [a for a in p.agendas.all() if a.activa]
        filas.append({"p": p, "horas": round(sum(a.minutos for a in activas) / 60, 1),
                      "policlinicos": sorted({a.policlinico.nombre for a in activas})})
    return render(request, "profesionales/lista.html", {
        "filas": filas, "form": form, "editar": editar, "abrir_modal": abrir_modal,
        "tabs": [("Equipo", reverse("profesionales:lista"), "equipo"),
                 ("Horario semanal", reverse("agenda:horario"), "horario"),
                 ("Bloquear y liberar horas", reverse("agenda:calendario"), "calendario")],
        "tab": "equipo",
    })


@solo_admin
@require_POST
def activar(request, pk):
    p = get_object_or_404(Profesional, pk=pk)
    p.activo = not p.activo
    servicio.guardar(p, request.user)
    if p.activo:
        messages.success(request, f"{p.nombre} vuelve a aparecer para agendar", extra_tags="toast")
    else:
        messages.success(request, f"{p.nombre} ya no aparece para agendar", extra_tags="toast")
    return redirect("profesionales:lista")


@solo_admin
def catalogo(request):
    """Especialidades y policlínicos (son conceptos distintos)."""
    return render(request, "profesionales/catalogo.html", {
        "especialidades": repo.especialidades(), "policlinicos": repo.policlinicos(),
    })


def _form(request, form_class, modelo, pk, titulo):
    instancia = get_object_or_404(modelo, pk=pk) if pk else None
    form = form_class(request.POST or None, instance=instancia)
    if request.method == "POST" and form.is_valid():
        obj = servicio.guardar(form.save(commit=False), request.user)
        messages.success(request, f"«{obj}» guardado", extra_tags="toast")
        return redirect("profesionales:catalogo")
    return render(request, "core/form_simple.html", {
        "form": form, "titulo": f"{'Editar' if instancia else 'Nuevo/a'} {titulo}", "url_volver": "profesionales:catalogo",
    })


@solo_admin
def especialidad_form(request, pk=None):
    return _form(request, EspecialidadForm, Especialidad, pk, "especialidad")


@solo_admin
def policlinico_form(request, pk=None):
    return _form(request, PoliclinicoForm, Policlinico, pk, "policlínico")

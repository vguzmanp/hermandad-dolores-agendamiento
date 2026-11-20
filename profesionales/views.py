from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

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
    esp = request.GET.get("especialidad") or None
    return render(request, "profesionales/lista.html", {
        "profesionales": repo.listar(especialidad_id=esp),
        "especialidades": Especialidad.objects.all(),
        "esp_sel": esp,
    })


@solo_admin
def especialidades(request):
    return render(request, "profesionales/especialidades.html", {"especialidades": repo.especialidades()})


@solo_admin
def policlinicos(request):
    return render(request, "profesionales/policlinicos.html", {"policlinicos": repo.policlinicos()})


def _form(request, form_class, modelo, pk, titulo, url_volver):
    instancia = get_object_or_404(modelo, pk=pk) if pk else None
    form = form_class(request.POST or None, instance=instancia)
    if request.method == "POST" and form.is_valid():
        obj = servicio.guardar(form.save(commit=False), request.user)
        messages.success(request, f"«{obj}» guardado correctamente.")
        return redirect(url_volver)
    return render(request, "core/form_simple.html", {
        "form": form, "titulo": f"{'Editar' if instancia else 'Nuevo/a'} {titulo}", "url_volver": url_volver,
    })


@solo_admin
def profesional_form(request, pk=None):
    return _form(request, ProfesionalForm, Profesional, pk, "profesional", "profesionales:lista")


@solo_admin
def especialidad_form(request, pk=None):
    return _form(request, EspecialidadForm, Especialidad, pk, "especialidad", "profesionales:especialidades")


@solo_admin
def policlinico_form(request, pk=None):
    return _form(request, PoliclinicoForm, Policlinico, pk, "policlínico", "profesionales:policlinicos")

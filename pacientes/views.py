from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core import roles
from core.exceptions import ReglaNegocioError

from .forms import AdultoResponsableForm, BuscarRutForm, PacienteForm
from .models import Paciente
from .services import PacienteService

servicio = PacienteService()


@roles.rol_requerido(roles.TENS, roles.ADMINISTRACION)
def lista(request):
    q = request.GET.get("q", "")
    pagina = Paginator(servicio.buscar(q), 20).get_page(request.GET.get("page"))
    return render(request, "pacientes/lista.html", {"pagina": pagina, "q": q})


@roles.rol_requerido(roles.TENS, roles.ADMINISTRACION)
def buscar_rut(request):
    """RF-02: se busca por RUT antes de registrar, para no duplicar pacientes."""
    form = BuscarRutForm(request.GET or None)
    if request.GET and form.is_valid():
        rut = form.cleaned_data["rut"]
        paciente = servicio.buscar_por_rut(rut)
        if paciente:
            messages.info(request, f"El paciente con RUT {paciente.rut_formateado} ya está registrado.")
            return redirect("pacientes:detalle", pk=paciente.pk)
        if roles.tiene_rol(request.user, roles.TENS):
            messages.warning(request, "No existe un paciente con ese RUT. Complete el registro.")
            return redirect(reverse("pacientes:crear") + f"?rut={rut}")
        messages.warning(request, "No existe un paciente con ese RUT.")
    return render(request, "pacientes/buscar_rut.html", {"form": form})


@roles.rol_requerido(roles.TENS, roles.ADMINISTRACION)
def detalle(request, pk):
    paciente = get_object_or_404(Paciente.objects.select_related("adulto_responsable"), pk=pk)
    citas = []
    if hasattr(paciente, "citas"):
        citas = paciente.citas.select_related(
            "cupo__agenda__profesional__especialidad", "cupo__agenda__policlinico"
        ).order_by("-cupo__fecha", "-cupo__hora_inicio")[:30]
    return render(request, "pacientes/detalle.html", {"paciente": paciente, "citas": citas})


def _guardar(request, instancia: Paciente | None):
    inicial = {"rut": request.GET.get("rut", "")} if instancia is None else None
    form = PacienteForm(request.POST or None, instance=instancia, initial=inicial)
    resp_inst = getattr(instancia, "adulto_responsable", None) if instancia else None
    form_resp = AdultoResponsableForm(request.POST or None, instance=resp_inst)

    if request.method == "POST" and form.is_valid():
        paciente = form.save(commit=False)
        necesita = paciente.necesita_responsable
        if not necesita or form_resp.is_valid():
            responsable = form_resp.save(commit=False) if necesita else None
            try:
                paciente = servicio.guardar(paciente, responsable, request.user)
            except ReglaNegocioError as e:
                messages.error(request, str(e))
            else:
                messages.success(request, f"Paciente {paciente.nombre} guardado correctamente.")
                for aviso in paciente.advertencias:
                    messages.warning(request, aviso)
                return redirect("pacientes:detalle", pk=paciente.pk)
        else:
            messages.error(request, "RN-04: complete los datos del adulto responsable.")

    return render(
        request,
        "pacientes/form.html",
        {"form": form, "form_resp": form_resp, "paciente": instancia},
    )


@roles.rol_requerido(roles.TENS)
def crear(request):
    return _guardar(request, None)


@roles.rol_requerido(roles.TENS)
def editar(request, pk):
    return _guardar(request, get_object_or_404(Paciente, pk=pk))

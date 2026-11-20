from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from core import roles
from core.exceptions import ReglaNegocioError

from .forms import AdultoResponsableForm, DocumentoForm, PacienteForm
from .models import DocumentoPaciente, Paciente
from .rut import normalizar_rut
from .services import DocumentoService, PacienteService

servicio = PacienteService()
documentos = DocumentoService()

tens_o_admin = roles.rol_requerido(roles.TENS, roles.ADMINISTRACION)


def _resultados(q):
    qs = servicio.buscar(q) if q else Paciente.objects.order_by("-fecha_registro")
    return qs[:12]


@tens_o_admin
def lista(request, pk=None):
    """Registro / edición de paciente (izquierda) y búsqueda (derecha)."""
    instancia = get_object_or_404(Paciente, pk=pk) if pk else None
    puede_editar = roles.tiene_rol(request.user, roles.TENS)
    q = request.GET.get("q", "").strip()
    form = form_resp = None
    if puede_editar:
        inicial = {"rut": request.GET.get("rut", "")} if instancia is None else None
        form = PacienteForm(request.POST or None, instance=instancia, initial=inicial)
        resp_inst = getattr(instancia, "adulto_responsable", None) if instancia else None
        form_resp = AdultoResponsableForm(request.POST or None, instance=resp_inst)
        if request.method == "POST" and form.is_valid():
            paciente = form.save(commit=False)
            necesita = paciente.necesita_responsable
            if not necesita or form_resp.is_valid():
                try:
                    paciente = servicio.guardar(paciente, form_resp.save(commit=False) if necesita else None, request.user)
                except ReglaNegocioError as e:
                    messages.error(request, str(e))
                else:
                    messages.success(request, f"Paciente {paciente.nombre} guardado", extra_tags="toast")
                    for aviso in paciente.advertencias:
                        messages.warning(request, aviso)
                    return redirect(reverse("pacientes:editar", args=[paciente.pk]))
    elif request.method == "POST":
        raise Http404
    return render(request, "pacientes/lista.html", {
        "form": form, "form_resp": form_resp, "paciente": instancia, "q": q, "resultados": _resultados(q),
    })


@tens_o_admin
def buscar_rut(request):
    """RF-02: si el RUT existe se abre su ficha; si no, el formulario de registro con el RUT."""
    rut = normalizar_rut(request.GET.get("rut", ""))
    p = servicio.buscar_por_rut(rut) if rut else None
    if p:
        return redirect("pacientes:editar", pk=p.pk)
    return redirect(reverse("pacientes:lista") + (f"?rut={rut}" if rut else ""))


# ------------------------------------------------------------------ documentos
@tens_o_admin
def documentos_paciente(request):
    pid = request.GET.get("paciente") or request.POST.get("paciente")
    paciente = Paciente.objects.filter(pk=pid).first() if pid and pid.isdigit() else None
    q = request.GET.get("q", "").strip()
    if paciente is None:
        return render(request, "pacientes/documentos.html", {"q": q, "resultados": _resultados(q)})
    form = DocumentoForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            documentos.adjuntar(paciente, form.cleaned_data["tipo"], form.cleaned_data["archivo"], request.user)
        except ReglaNegocioError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, "Documento adjuntado", extra_tags="toast")
            return redirect(f"{reverse('documentos:lista')}?paciente={paciente.pk}")
    if not form.is_bound and not paciente.inscrito_cesfam:
        form.initial["tipo"] = DocumentoPaciente.Tipo.CESFAM
    return render(request, "pacientes/documentos.html", {
        "paciente": paciente, "form": form,
        "docs": paciente.documentos.select_related("subido_por"),
        "historial": paciente.operaciones_documentos.select_related("usuario")[:30],
    })


@xframe_options_sameorigin
@tens_o_admin
def documento_archivo(request, pk):
    """Muestra el archivo (dentro del modal «Ver») y registra la consulta en el historial."""
    doc = get_object_or_404(DocumentoPaciente, pk=pk)
    documentos.registrar_consulta(doc, request.user)
    if not doc.archivo:
        return render(request, "pacientes/documento_ejemplo.html", {"doc": doc})
    return FileResponse(doc.archivo.open("rb"), filename=doc.nombre, as_attachment=False)


@tens_o_admin
@require_POST
def documento_eliminar(request, pk):
    doc = get_object_or_404(DocumentoPaciente, pk=pk)
    pid = doc.paciente_id
    documentos.eliminar(doc, request.user)
    messages.success(request, "Documento eliminado", extra_tags="toast")
    return redirect(f"{reverse('documentos:lista')}?paciente={pid}")

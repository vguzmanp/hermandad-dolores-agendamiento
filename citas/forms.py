from django import forms
from django.conf import settings

from core.forms import BootstrapFormMixin, FechaInput
from pacientes.repositories import PacienteRepository
from pacientes.rut import validar_rut
from profesionales.models import Especialidad, Policlinico, Profesional

from .models import Cita


class DisponibilidadForm(BootstrapFormMixin, forms.Form):
    especialidad = forms.ModelChoiceField(Especialidad.objects.filter(activa=True), required=False, empty_label="Todas")
    profesional = forms.ModelChoiceField(
        Profesional.objects.filter(activo=True).select_related("especialidad"), required=False, empty_label="Todos"
    )
    policlinico = forms.ModelChoiceField(Policlinico.objects.filter(activo=True), required=False,
                                         empty_label="Todos", label="Policlínico")
    desde = forms.DateField(required=False, widget=FechaInput())
    hasta = forms.DateField(required=False, widget=FechaInput())
    paciente = forms.IntegerField(required=False, widget=forms.HiddenInput())

    def clean(self):
        d = super().clean()
        if d.get("desde") and d.get("hasta") and d["hasta"] < d["desde"]:
            self.add_error("hasta", "Debe ser posterior a la fecha inicial.")
        return d


class AgendarForm(BootstrapFormMixin, forms.Form):
    rut = forms.CharField(label="RUT del paciente", max_length=12)
    sesiones = forms.IntegerField(label="Número de sesiones a agendar", min_value=1, initial=1)
    dias_aviso = forms.IntegerField(label="Días de aviso para el recordatorio", min_value=0, max_value=14,
                                    initial=settings.CITA_DIAS_AVISO_DEFECTO)
    observaciones = forms.CharField(max_length=300, required=False)

    def __init__(self, *args, max_sesiones: int = 1, sobrecupo: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.paciente = None
        if sobrecupo or max_sesiones <= 1:
            del self.fields["sesiones"]
        else:
            self.fields["sesiones"].max_value = max_sesiones
            self.fields["sesiones"].widget.attrs["max"] = max_sesiones
            self.fields["sesiones"].help_text = (
                f"Esta especialidad permite agendar hasta {max_sesiones} sesiones de una vez "
                f"(mismo profesional, policlínico y hora, en las fechas siguientes)."
            )

    def clean_rut(self):
        rut = validar_rut(self.cleaned_data["rut"])
        self.paciente = PacienteRepository().buscar_por_rut(rut)
        if self.paciente is None:
            raise forms.ValidationError("No existe un paciente con ese RUT. Regístrelo primero.")
        return rut


class FiltroCitasForm(BootstrapFormMixin, forms.Form):
    desde = forms.DateField(required=False, widget=FechaInput())
    hasta = forms.DateField(required=False, widget=FechaInput())
    profesional = forms.ModelChoiceField(Profesional.objects.all(), required=False, empty_label="Todos")
    policlinico = forms.ModelChoiceField(Policlinico.objects.all(), required=False, empty_label="Todos", label="Policlínico")
    estado = forms.ChoiceField(choices=[("", "Todos")] + list(Cita.Estado.choices), required=False)

    def __init__(self, *args, policlinico=None, **kwargs):
        super().__init__(*args, **kwargs)
        if policlinico:  # la TENS/TONS solo ve su policlínico
            del self.fields["policlinico"]
            self.fields["profesional"].queryset = Profesional.objects.filter(
                agendas__policlinico=policlinico).distinct()

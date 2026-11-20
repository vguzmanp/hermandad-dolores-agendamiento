from django import forms
from django.utils import timezone

from core.forms import BootstrapFormMixin, FechaInput

from .models import AdultoResponsable, Paciente
from .repositories import PacienteRepository
from .rut import validar_rut


class BuscarRutForm(BootstrapFormMixin, forms.Form):
    rut = forms.CharField(label="RUT del paciente", max_length=12, widget=forms.TextInput(attrs={"placeholder": "12.345.678-9", "autofocus": True}))

    def clean_rut(self):
        return validar_rut(self.cleaned_data["rut"])


class PacienteForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Paciente
        fields = [
            "rut", "nombre", "fecha_nacimiento", "sexo", "nacionalidad",
            "celular", "correo", "direccion",
            "inscrito_cesfam", "cesfam", "requiere_responsable", "observaciones",
        ]
        widgets = {
            "fecha_nacimiento": FechaInput(),
            "observaciones": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_rut(self):
        rut = validar_rut(self.cleaned_data["rut"])
        if PacienteRepository().existe_rut(rut, excluir_id=self.instance.pk):
            raise forms.ValidationError("Ya existe un paciente con este RUT (RF-02). Búsquelo en el listado.")
        return rut

    def clean_fecha_nacimiento(self):
        f = self.cleaned_data["fecha_nacimiento"]
        if f > timezone.localdate():
            raise forms.ValidationError("La fecha de nacimiento no puede ser futura.")
        return f

    def clean(self):
        datos = super().clean()
        if datos.get("inscrito_cesfam") and not datos.get("cesfam"):
            self.add_error("cesfam", "Indique el CESFAM de inscripción.")
        return datos


class AdultoResponsableForm(BootstrapFormMixin, forms.ModelForm):
    prefix = "resp"

    class Meta:
        model = AdultoResponsable
        fields = ["nombre", "rut", "parentesco", "celular", "correo"]

    def clean_rut(self):
        return validar_rut(self.cleaned_data["rut"])

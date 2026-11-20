from django import forms
from django.utils import timezone

from core.forms import BootstrapFormMixin, FechaInput

from .models import AdultoResponsable, DocumentoPaciente, Paciente
from .repositories import PacienteRepository
from .rut import validar_rut

NACIONALIDADES = ["Chilena", "Venezolana", "Peruana", "Haitiana", "Colombiana", "Boliviana", "Argentina",
                  "Ecuatoriana", "Dominicana", "Otra"]
PARENTESCOS = ["Madre", "Padre", "Abuelo/a", "Hermano/a", "Hijo/a", "Tutor/a legal", "Cuidador/a", "Otro"]


class BuscarRutForm(BootstrapFormMixin, forms.Form):
    rut = forms.CharField(label="RUT del paciente", max_length=12,
                          widget=forms.TextInput(attrs={"placeholder": "12.345.678-5", "autofocus": True}))

    def clean_rut(self):
        return validar_rut(self.cleaned_data["rut"])


class PacienteForm(BootstrapFormMixin, forms.ModelForm):
    nacionalidad = forms.ChoiceField(choices=[(n, n) for n in NACIONALIDADES])

    class Meta:
        model = Paciente
        fields = ["nombre", "rut", "fecha_nacimiento", "celular", "correo", "direccion", "sexo", "nacionalidad",
                  "requiere_responsable"]
        labels = {"celular": "Teléfono celular", "correo": "Correo electrónico (opcional)", "sexo": "Género",
                  "requiere_responsable": "Es menor de edad o necesita un adulto responsable"}
        help_texts = {"correo": "Puede quedar vacío", "requiere_responsable": "", "rut": ""}
        widgets = {
            "fecha_nacimiento": FechaInput(),
            "rut": forms.TextInput(attrs={"placeholder": "12.345.678-5"}),
            "celular": forms.TextInput(attrs={"placeholder": "+56 9 1234 5678"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        actual = self.instance.nacionalidad if self.instance.pk else None
        if actual and actual not in NACIONALIDADES:
            self.fields["nacionalidad"].choices = [(actual, actual)] + self.fields["nacionalidad"].choices
        self.fields["sexo"].choices = [("", "Selecciona")] + list(Paciente.Sexo.choices)
        if self.instance.pk:  # el RUT no se cambia una vez registrado
            self.fields["rut"].disabled = True

    def clean_rut(self):
        if self.instance.pk:
            return self.instance.rut
        rut = validar_rut(self.cleaned_data["rut"])
        if PacienteRepository().existe_rut(rut):
            raise forms.ValidationError("Ya existe un paciente con este RUT. Búsquelo a la derecha.")
        return rut

    def clean_fecha_nacimiento(self):
        f = self.cleaned_data["fecha_nacimiento"]
        if f > timezone.localdate():
            raise forms.ValidationError("La fecha de nacimiento no puede ser futura.")
        return f


class AdultoResponsableForm(BootstrapFormMixin, forms.ModelForm):
    prefix = "resp"
    parentesco = forms.ChoiceField(label="Relación con el paciente", choices=[(p, p) for p in PARENTESCOS])

    class Meta:
        model = AdultoResponsable
        fields = ["nombre", "rut", "celular", "parentesco"]
        labels = {"nombre": "Nombre del adulto responsable", "rut": "RUT del adulto responsable",
                  "celular": "Teléfono del adulto responsable"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        actual = self.instance.parentesco if self.instance.pk else None
        if actual and actual not in PARENTESCOS:
            self.fields["parentesco"].choices = [(actual, actual)] + self.fields["parentesco"].choices

    def clean_rut(self):
        return validar_rut(self.cleaned_data["rut"])


class DocumentoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DocumentoPaciente
        fields = ["tipo", "archivo"]
        help_texts = {"archivo": "PDF, JPG o PNG."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["archivo"].required = True
        self.fields["archivo"].widget.attrs["accept"] = ".pdf,.jpg,.jpeg,.png"

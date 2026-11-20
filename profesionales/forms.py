from django import forms
from django.contrib.auth.models import User

from core import roles
from core.forms import BootstrapFormMixin
from pacientes.rut import validar_rut

from .models import Especialidad, Policlinico, Profesional


class ProfesionalForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Profesional
        fields = ["nombre", "rut", "especialidad", "usuario"]
        labels = {"nombre": "Nombre y título", "usuario": "Usuario del sistema (opcional)"}
        help_texts = {"usuario": "Para que vea sus citas y estadísticas con el rol Profesional."}
        widgets = {"nombre": forms.TextInput(attrs={"placeholder": "Dra. Ana Torres"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["especialidad"].queryset = Especialidad.objects.filter(activa=True)
        self.fields["usuario"].queryset = User.objects.filter(groups__name=roles.PROFESIONAL)

    def clean_rut(self):
        return validar_rut(self.cleaned_data["rut"])


class EspecialidadForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Especialidad
        fields = ["nombre", "duracion_cupo_min", "sesiones_por_tratamiento", "permite_agendar_todas_sesiones", "activa"]

    def clean(self):
        d = super().clean()
        if d.get("permite_agendar_todas_sesiones") and (d.get("sesiones_por_tratamiento") or 1) < 2:
            self.add_error("sesiones_por_tratamiento", "Indique cuántas sesiones tiene el tratamiento (2 o más).")
        return d


class PoliclinicoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Policlinico
        fields = ["nombre", "direccion", "es_telemedicina", "activo"]

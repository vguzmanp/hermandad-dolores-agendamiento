from django import forms
from django.contrib.auth.models import User
from django.db.models import Q

from core import roles
from core.forms import BootstrapFormMixin
from pacientes.rut import validar_rut

from .models import Especialidad, Policlinico, Profesional


class ProfesionalForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Profesional
        fields = ["nombre", "rut", "especialidad"]
        labels = {"nombre": "Nombre y título"}
        widgets = {"nombre": forms.TextInput(attrs={"placeholder": "Dra. Ana Torres"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["especialidad"].queryset = Especialidad.objects.filter(activa=True)

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
        fields = ["nombre", "direccion", "es_telemedicina", "usuario_tens", "activo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        libres = User.objects.filter(groups__name=roles.TENS, is_superuser=False)
        if self.instance.pk:
            libres = libres.filter(Q(policlinico_tens__isnull=True) | Q(policlinico_tens=self.instance))
        else:
            libres = libres.filter(policlinico_tens__isnull=True)
        self.fields["usuario_tens"].queryset = libres.order_by("username")
        self.fields["usuario_tens"].label_from_instance = lambda u: u.username

from datetime import timedelta

from django import forms
from django.conf import settings
from django.utils import timezone

from core.forms import BootstrapFormMixin, FechaInput, HoraInput
from profesionales.models import Policlinico, Profesional

from .models import Agenda


class AgendaForm(BootstrapFormMixin, forms.ModelForm):
    generar_semanas = forms.IntegerField(
        label="Generar cupos para las próximas N semanas", min_value=0, max_value=26, required=False,
        initial=settings.AGENDA_SEMANAS_GENERACION, help_text="0 = no generar ahora.",
    )

    class Meta:
        model = Agenda
        fields = ["profesional", "policlinico", "dia_semana", "hora_inicio", "hora_fin",
                  "duracion_cupo_min", "vigente_desde", "vigente_hasta", "activa"]
        widgets = {
            "hora_inicio": HoraInput(), "hora_fin": HoraInput(),
            "vigente_desde": FechaInput(), "vigente_hasta": FechaInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["profesional"].queryset = Profesional.objects.filter(activo=True).select_related("especialidad")
        self.fields["policlinico"].queryset = Policlinico.objects.filter(activo=True)
        if not self.instance.pk:
            self.fields["vigente_desde"].initial = timezone.localdate()
        else:
            self.fields["generar_semanas"].initial = 0


class GenerarCuposForm(BootstrapFormMixin, forms.Form):
    desde = forms.DateField(widget=FechaInput())
    hasta = forms.DateField(widget=FechaInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoy = timezone.localdate()
        self.fields["desde"].initial = hoy
        self.fields["hasta"].initial = hoy + timedelta(weeks=settings.AGENDA_SEMANAS_GENERACION)

    def clean(self):
        d = super().clean()
        if d.get("desde") and d.get("hasta") and d["hasta"] < d["desde"]:
            raise forms.ValidationError("La fecha final debe ser posterior a la inicial.")
        if d.get("desde") and d.get("hasta") and (d["hasta"] - d["desde"]).days > 366:
            raise forms.ValidationError("El rango máximo de generación es de un año.")
        return d


class BloquearDiaForm(BootstrapFormMixin, forms.Form):
    fecha = forms.DateField(widget=FechaInput())
    motivo = forms.CharField(max_length=200, required=False, widget=forms.TextInput(attrs={"placeholder": "Ej: feriado, licencia médica"}))

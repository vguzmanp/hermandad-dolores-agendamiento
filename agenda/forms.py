from datetime import time

from django import forms

from core.forms import BootstrapFormMixin
from profesionales.models import Policlinico

from .models import Agenda

HORAS = [time(h, m) for h in range(7, 21) for m in (0, 30)] + [time(21, 0)]
OPCIONES_HORA = [(t.strftime("%H:%M"), t.strftime("%H:%M")) for t in HORAS]


class BloqueSemanalForm(BootstrapFormMixin, forms.Form):
    dia_semana = forms.TypedChoiceField(label="Día", coerce=int, choices=Agenda.DiaSemana.choices[:6])
    policlinico = forms.ModelChoiceField(label="Policlínico", queryset=Policlinico.objects.filter(activo=True))
    hora_inicio = forms.ChoiceField(label="Desde", choices=OPCIONES_HORA, initial="09:00")
    hora_fin = forms.ChoiceField(label="Hasta", choices=OPCIONES_HORA, initial="12:00")

    def clean(self):
        d = super().clean()
        if d.get("hora_inicio") and d.get("hora_fin"):
            d["hora_inicio"] = time.fromisoformat(d["hora_inicio"])
            d["hora_fin"] = time.fromisoformat(d["hora_fin"])
            if d["hora_fin"] <= d["hora_inicio"]:
                self.add_error("hora_fin", "Debe ser posterior a la hora de inicio.")
        return d

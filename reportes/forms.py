"""Filtros de los reportes de Administración (todos opcionales y combinables)."""
from django import forms

from citas.models import Cita
from core.forms import BootstrapFormMixin, FechaInput
from pacientes.models import Paciente
from profesionales.models import Especialidad, Policlinico, Profesional

PERIODOS = [("1m", "Último mes"), ("3m", "Últimos 3 meses"), ("6m", "Últimos 6 meses"),
            ("12m", "Últimos 12 meses"), ("todo", "Todo el historial"), ("rango", "Rango de fechas…")]
TRAMOS_EDAD = [("0-14", "0–14 años", 0, 14), ("15-17", "15–17 años", 15, 17), ("18-29", "18–29 años", 18, 29),
               ("30-59", "30–59 años", 30, 59), ("60-200", "60 años o más", 60, 200)]
SI_NO = [("", "Todos"), ("si", "Sí"), ("no", "No")]


class FiltroReporteForm(BootstrapFormMixin, forms.Form):
    # período
    periodo = forms.ChoiceField(choices=PERIODOS, required=False, initial="3m", label="Período")
    desde = forms.DateField(required=False, widget=FechaInput())
    hasta = forms.DateField(required=False, widget=FechaInput())
    # dónde y con quién
    policlinico = forms.ModelChoiceField(Policlinico.objects.all(), required=False, empty_label="Todos",
                                         label="Policlínico")
    especialidad = forms.ModelChoiceField(Especialidad.objects.all(), required=False, empty_label="Todas")
    profesional = forms.ModelChoiceField(Profesional.objects.select_related("especialidad"), required=False,
                                         empty_label="Todos")
    # la cita
    estado = forms.ChoiceField(choices=[("", "Todos")] + list(Cita.Estado.choices), required=False,
                               label="Estado de la cita")
    asistencia = forms.ChoiceField(choices=[("", "Todas"), ("asistio", "Asistió"), ("no_asistio", "No asistió"),
                                            ("sin_registro", "Sin registro")], required=False)
    canal = forms.ChoiceField(choices=[("", "Todos")] + list(Cita.Canal.choices), required=False,
                              label="¿Cómo pidió la hora?")
    sobrecupo = forms.ChoiceField(choices=SI_NO, required=False, label="Sobrecupo")
    # el paciente
    sexo = forms.ChoiceField(choices=[("", "Todos")] + list(Paciente.Sexo.choices), required=False)
    edad = forms.ChoiceField(choices=[("", "Todas")] + [(k, t) for k, t, _, _ in TRAMOS_EDAD], required=False,
                             label="Tramo de edad")
    nacionalidad = forms.ChoiceField(choices=[], required=False)

    responsable = forms.ChoiceField(choices=SI_NO, required=False, label="Con adulto responsable")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        nacs = Paciente.objects.order_by("nacionalidad").values_list("nacionalidad", flat=True).distinct()
        self.fields["nacionalidad"].choices = [("", "Todas")] + [(n, n) for n in nacs]

    def clean(self):
        d = super().clean()
        if d.get("periodo") == "rango":
            if not d.get("desde") and not d.get("hasta"):
                self.add_error("desde", "Indique al menos una fecha.")
            if d.get("desde") and d.get("hasta") and d["hasta"] < d["desde"]:
                self.add_error("hasta", "Debe ser posterior a la fecha inicial.")
        return d


class FiltroPacientesForm(FiltroReporteForm):
    """Filtros adicionales del reporte de pacientes."""

    CAMPOS_ORDEN = ["nombre", "edad", "nacionalidad", "n_citas", "n_asistidas", "n_inasistencias", "n_canceladas",
                    "ultima_atencion", "proxima_cita", "fecha_registro"]
    ORDENES = [(f"{s}{c}", f"{s}{c}") for c in CAMPOS_ORDEN for s in ("", "-")]

    q = forms.CharField(required=False, label="Nombre o RUT")
    en_espera = forms.ChoiceField(choices=SI_NO, required=False, label="En lista de espera")
    con_inasistencias = forms.ChoiceField(choices=SI_NO, required=False, label="Con inasistencias")
    sin_citas = forms.BooleanField(required=False, label="Incluir pacientes sin citas en el período")
    orden = forms.ChoiceField(choices=ORDENES, required=False, initial="nombre", label="Ordenar por")

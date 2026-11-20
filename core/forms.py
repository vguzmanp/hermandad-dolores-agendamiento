from django import forms


class BootstrapFormMixin:
    """Agrega las clases CSS de Bootstrap 5 a todos los campos del formulario."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            w = campo.widget
            if isinstance(w, (forms.CheckboxInput,)):
                w.attrs.setdefault("class", "form-check-input")
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs.setdefault("class", "form-select")
            elif isinstance(w, forms.RadioSelect):
                continue
            else:
                w.attrs.setdefault("class", "form-control")


class FechaInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None, format="%Y-%m-%d"):
        super().__init__(attrs=attrs, format=format)


class HoraInput(forms.TimeInput):
    input_type = "time"

    def __init__(self, attrs=None, format="%H:%M"):
        super().__init__(attrs=attrs, format=format)

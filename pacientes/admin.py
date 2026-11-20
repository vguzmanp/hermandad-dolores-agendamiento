from django.contrib import admin

from .models import AdultoResponsable, Paciente


class AdultoResponsableInline(admin.StackedInline):
    model = AdultoResponsable
    extra = 0


@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "rut", "celular", "fecha_nacimiento", "inscrito_cesfam")
    search_fields = ("nombre", "rut")
    list_filter = ("sexo", "inscrito_cesfam", "nacionalidad")
    inlines = [AdultoResponsableInline]

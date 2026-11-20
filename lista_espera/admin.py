from django.contrib import admin

from .models import SolicitudEspera


@admin.register(SolicitudEspera)
class SolicitudEsperaAdmin(admin.ModelAdmin):
    list_display = ("orden", "paciente", "especialidad", "profesional", "estado", "creada_en")
    list_filter = ("estado", "especialidad")

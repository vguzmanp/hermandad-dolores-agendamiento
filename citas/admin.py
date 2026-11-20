from django.contrib import admin

from .models import Cita, MensajeEnviado


@admin.register(Cita)
class CitaAdmin(admin.ModelAdmin):
    list_display = ("paciente", "cupo", "estado", "es_sobrecupo", "dias_aviso", "creada_en")
    list_filter = ("estado", "es_sobrecupo", "cupo__agenda__policlinico")
    search_fields = ("paciente__nombre", "paciente__rut")
    raw_id_fields = ("cupo", "paciente", "cita_original")


@admin.register(MensajeEnviado)
class MensajeEnviadoAdmin(admin.ModelAdmin):
    list_display = ("enviado_en", "tipo", "destinatario", "paciente")
    list_filter = ("tipo",)

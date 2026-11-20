from django.contrib import admin

from .models import Agenda, Cupo


@admin.register(Agenda)
class AgendaAdmin(admin.ModelAdmin):
    list_display = ("profesional", "policlinico", "dia_semana", "hora_inicio", "hora_fin", "activa")
    list_filter = ("policlinico", "dia_semana", "activa")


@admin.register(Cupo)
class CupoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "hora_inicio", "agenda", "bloqueado")
    list_filter = ("bloqueado", "agenda__policlinico")
    date_hierarchy = "fecha"

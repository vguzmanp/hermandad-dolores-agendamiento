from django.contrib import admin

from .models import Especialidad, Policlinico, Profesional

admin.site.register(Policlinico)
admin.site.register(Especialidad)


@admin.register(Profesional)
class ProfesionalAdmin(admin.ModelAdmin):
    list_display = ("nombre", "rut", "especialidad", "usuario", "activo")
    list_filter = ("especialidad", "activo")
    search_fields = ("nombre", "rut")

from django.urls import path

from core.views import pendiente

app_name = "citas"

urlpatterns = [
    path("", pendiente("Citas", 4), name="disponibilidad"),
    path("lista/", pendiente("Citas", 4), name="lista"),
    path("recordatorios/", pendiente("Citas", 4), name="recordatorios"),
    path("mensajes/", pendiente("Citas", 4), name="mensajes"),
]

from django.urls import path

from core.views import pendiente

app_name = "asistencia"

urlpatterns = [
    path("", pendiente("Asistencia", 5), name="lista"),
]

from django.urls import path

from core.views import pendiente

app_name = "profesionales"

urlpatterns = [
    path("", pendiente("Profesionales", 3), name="lista"),
    path("especialidades/", pendiente("Profesionales", 3), name="especialidades"),
    path("policlinicos/", pendiente("Profesionales", 3), name="policlinicos"),
]

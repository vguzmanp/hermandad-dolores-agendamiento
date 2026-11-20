from django.urls import path

from core.views import pendiente

app_name = "pacientes"

urlpatterns = [
    path("", pendiente("Pacientes", 2), name="lista"),
    path("buscar_rut/", pendiente("Pacientes", 2), name="buscar_rut"),
    path("crear/", pendiente("Pacientes", 2), name="crear"),
]

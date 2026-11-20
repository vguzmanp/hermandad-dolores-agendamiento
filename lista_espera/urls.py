from django.urls import path

from core.views import pendiente

app_name = "lista_espera"

urlpatterns = [
    path("", pendiente("Lista de espera", 6), name="lista"),
]

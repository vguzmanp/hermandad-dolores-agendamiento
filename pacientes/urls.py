from django.urls import path

from . import views

app_name = "pacientes"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("buscar/", views.buscar_rut, name="buscar_rut"),
    path("<int:pk>/", views.lista, name="editar"),
]

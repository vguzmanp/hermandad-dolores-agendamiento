from django.urls import path

from . import views

app_name = "lista_espera"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:pk>/gestionar/", views.gestionar, name="gestionar"),
]

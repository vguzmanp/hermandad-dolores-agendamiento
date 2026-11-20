from django.urls import path

from . import views

app_name = "asistencia"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:pk>/registrar/", views.registrar, name="registrar"),
]

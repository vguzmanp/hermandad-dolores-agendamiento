from django.urls import path

from . import views

app_name = "reportes"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("demanda.csv", views.csv_demanda, name="csv"),
    path("pacientes.csv", views.csv_pacientes, name="csv_pacientes"),
    path("pacientes/<int:pk>/", views.paciente, name="paciente"),
    path("pacientes/<int:pk>/historial.csv", views.csv_paciente, name="csv_paciente"),
]

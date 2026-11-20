from django.urls import path

from . import views

app_name = "reportes"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("demanda.csv", views.csv_demanda, name="csv"),
]

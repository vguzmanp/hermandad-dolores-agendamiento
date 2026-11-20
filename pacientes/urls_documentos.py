from django.urls import path

from . import views

app_name = "documentos"

urlpatterns = [
    path("", views.documentos_paciente, name="lista"),
    path("<int:pk>/archivo/", views.documento_archivo, name="archivo"),
    path("<int:pk>/eliminar/", views.documento_eliminar, name="eliminar"),
]

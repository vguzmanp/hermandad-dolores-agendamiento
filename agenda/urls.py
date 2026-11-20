from django.urls import path

from . import views

app_name = "agenda"

urlpatterns = [
    path("calendario/", views.calendario, name="calendario"),
    path("calendario/accion/", views.calendario_accion, name="calendario_accion"),
    path("horario/", views.horario, name="horario"),
    path("horario/<int:pk>/quitar/", views.quitar_bloque, name="quitar_bloque"),
]

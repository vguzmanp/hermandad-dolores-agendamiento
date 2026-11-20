from django.urls import path

from . import views

app_name = "citas"

urlpatterns = [
    path("", views.disponibilidad, name="disponibilidad"),
    path("lista/", views.lista, name="lista"),
    path("cupo/<int:cupo_id>/agendar/", views.agendar, name="agendar"),
    path("cupo/<int:cupo_id>/sobrecupo/", views.sobrecupo, name="sobrecupo"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/accion/<str:accion>/", views.accion, name="accion"),
    path("recordatorios/", views.recordatorios, name="recordatorios"),
    path("recordatorios/enviar-todos/", views.enviar_todos, name="enviar_todos"),
    path("mensajes/", views.mensajes, name="mensajes"),
]

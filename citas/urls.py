from django.urls import path

from . import views

app_name = "citas"

urlpatterns = [
    path("", views.redirigir_agendar, name="inicio"),
    path("agendar/", views.agendar, name="agendar"),
    path("lista/", views.lista, name="lista"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/accion/<str:accion>/", views.accion, name="accion"),
    path("avisos/enviar-pendientes/", views.enviar_todos, name="enviar_todos"),
    path("mensajes/", views.mensajes, name="mensajes"),
]

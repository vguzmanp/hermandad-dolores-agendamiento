from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("reservar/", views.inicio, name="inicio"),
    path("reservar/horas/", views.horas, name="horas"),
    path("reservar/datos/", views.datos, name="datos"),
    path("reservar/confirmar/", views.confirmar, name="confirmar"),
    path("reservar/listo/<str:token>/", views.listo, name="listo"),
    path("reservar/lista-de-espera/", views.espera_ok, name="espera_ok"),
    path("avisos/<str:token>/", views.aviso, name="aviso"),
    path("c/<str:token>/", views.responder, name="responder"),
    path("c/<str:token>/cambiar/", views.cambiar, name="cambiar"),
    path("c/<str:token>/resultado/", views.resultado, name="resultado"),
    path("c/<str:token>/<str:accion>/", views.responder_accion, name="accion"),
]

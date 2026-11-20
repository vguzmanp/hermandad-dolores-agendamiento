from django.urls import path

from . import views

app_name = "agenda"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("nueva/", views.agenda_form, name="crear"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/editar/", views.agenda_form, name="editar"),
    path("<int:pk>/generar/", views.generar, name="generar"),
    path("<int:pk>/bloquear-dia/", views.bloquear_dia, name="bloquear_dia"),
    path("cupos/<int:pk>/bloquear/", views.bloquear_cupo, name="bloquear_cupo"),
    path("cupos/<int:pk>/liberar/", views.liberar_cupo, name="liberar_cupo"),
]

from django.urls import path

from . import views

app_name = "profesionales"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:pk>/activar/", views.activar, name="activar"),
    path("catalogo/", views.catalogo, name="catalogo"),
    path("especialidades/nueva/", views.especialidad_form, name="especialidad_crear"),
    path("especialidades/<int:pk>/editar/", views.especialidad_form, name="especialidad_editar"),
    path("policlinicos/nuevo/", views.policlinico_form, name="policlinico_crear"),
    path("policlinicos/<int:pk>/editar/", views.policlinico_form, name="policlinico_editar"),
]

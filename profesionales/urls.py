from django.urls import path

from . import views

app_name = "profesionales"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("nuevo/", views.profesional_form, name="crear"),
    path("<int:pk>/editar/", views.profesional_form, name="editar"),
    path("especialidades/", views.especialidades, name="especialidades"),
    path("especialidades/nueva/", views.especialidad_form, name="especialidad_crear"),
    path("especialidades/<int:pk>/editar/", views.especialidad_form, name="especialidad_editar"),
    path("policlinicos/", views.policlinicos, name="policlinicos"),
    path("policlinicos/nuevo/", views.policlinico_form, name="policlinico_crear"),
    path("policlinicos/<int:pk>/editar/", views.policlinico_form, name="policlinico_editar"),
]

from django.urls import path

from core.views import pendiente

app_name = "agenda"

urlpatterns = [
    path("", pendiente("Agendas y cupos", 3), name="lista"),
]

from django.urls import path

from core.views import pendiente

app_name = "reportes"

urlpatterns = [
    path("", pendiente("Reportes", 6), name="inicio"),
]

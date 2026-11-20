from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from core import views as core_views

urlpatterns = [
    path("", core_views.home, name="home"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(extra_context={"debug_demo": settings.DEBUG}),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("pacientes/", include("pacientes.urls")),
    path("documentos/", include("pacientes.urls_documentos")),
    path("profesionales/", include("profesionales.urls")),
    path("agenda/", include("agenda.urls")),
    path("citas/", include("citas.urls")),
    path("lista-espera/", include("lista_espera.urls")),
    path("asistencia/", include("asistencia.urls")),
    path("reportes/", include("reportes.urls")),
    path("admin/", admin.site.urls),
    path("", include("portal.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

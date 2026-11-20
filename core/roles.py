"""Roles del sistema, implementados como grupos de Django."""
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

ADMINISTRACION = "Administración"
TENS = "TENS/TONS"
PROFESIONAL = "Profesional"

TODOS_LOS_ROLES = (ADMINISTRACION, TENS, PROFESIONAL)


def tiene_rol(usuario, *roles: str) -> bool:
    """True si el usuario pertenece a alguno de los roles (el superusuario siempre pasa)."""
    if not usuario or not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True
    nombres = getattr(usuario, "_roles_cache", None)
    if nombres is None:
        nombres = set(usuario.groups.values_list("name", flat=True))
        usuario._roles_cache = nombres
    return bool(nombres.intersection(roles))


def exigir_rol(usuario, *roles: str) -> None:
    """Usado en la capa de servicios: lanza PermissionDenied si no tiene el rol."""
    if not tiene_rol(usuario, *roles):
        raise PermissionDenied("Su rol no tiene permiso para realizar esta acción.")


class RolRequeridoMixin(LoginRequiredMixin):
    """Mixin para vistas basadas en clases. Define `roles = (TENS, ...)`."""

    roles: tuple[str, ...] = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if self.roles and not tiene_rol(request.user, *self.roles):
            raise PermissionDenied("Su rol no tiene acceso a esta sección.")
        return super().dispatch(request, *args, **kwargs)


def rol_requerido(*roles: str):
    """Decorador para vistas basadas en funciones."""

    def decorador(vista):
        @login_required
        def envoltura(request, *args, **kwargs):
            if roles and not tiene_rol(request.user, *roles):
                raise PermissionDenied("Su rol no tiene acceso a esta sección.")
            return vista(request, *args, **kwargs)

        envoltura.__name__ = vista.__name__
        envoltura.__doc__ = vista.__doc__
        return envoltura

    return decorador

"""Roles del sistema, implementados como grupos de Django."""
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

ADMINISTRACION = "Administración"
TENS = "TENS/TONS"

# Los profesionales no usan el sistema: solo la Administración y las TENS/TONS tienen cuenta.
TODOS_LOS_ROLES = (ADMINISTRACION, TENS)


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


def policlinico_de(usuario):
    """
    Policlínico en el que trabaja una TENS/TONS (cada policlínico tiene su propio
    usuario, con el nombre del policlínico). None = ve todos los policlínicos
    (Administración o superusuario).
    """
    if not usuario or not usuario.is_authenticated or usuario.is_superuser:
        return None
    if not tiene_rol(usuario, TENS):
        return None
    if hasattr(usuario, "_policlinico_cache"):
        return usuario._policlinico_cache
    from profesionales.models import Policlinico

    pol = Policlinico.objects.filter(usuario_tens=usuario).first()
    if pol is None and not tiene_rol(usuario, ADMINISTRACION):
        raise PermissionDenied("Su usuario TENS/TONS no está asociado a ningún policlínico.")
    usuario._policlinico_cache = pol
    return pol


def exigir_policlinico(usuario, policlinico) -> None:
    """Una TENS/TONS solo puede operar sobre su propio policlínico."""
    propio = policlinico_de(usuario)
    if propio is None:
        return
    if policlinico is None or propio.pk != getattr(policlinico, "pk", policlinico):
        raise PermissionDenied(f"Solo puede operar en el {propio.nombre}.")


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

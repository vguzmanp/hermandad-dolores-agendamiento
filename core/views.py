from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from . import roles as r


@login_required
def home(request):
    """Panel de inicio: muestra accesos según el rol del usuario."""
    contexto = {}
    # Indicadores del día (se completan a medida que existen los módulos).
    try:
        from citas.services import resumen_del_dia

        contexto["resumen"] = resumen_del_dia(request.user)
    except ImportError:  # pragma: no cover - módulo aún no construido
        contexto["resumen"] = None
    return render(request, "core/home.html", contexto)


def pendiente(nombre_modulo: str, etapa: int):
    """Genera una vista 'en construcción' para módulos de etapas futuras."""

    @login_required
    def vista(request, *args, **kwargs):
        return render(request, "core/pendiente.html", {"modulo": nombre_modulo, "etapa": etapa})

    vista.__name__ = f"pendiente_{nombre_modulo}"
    return vista


__all__ = ["home", "pendiente", "r"]

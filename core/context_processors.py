from . import roles as r


def roles(request):
    """Expone a las plantillas los flags de rol del usuario actual."""
    u = getattr(request, "user", None)
    return {
        "es_admin": r.tiene_rol(u, r.ADMINISTRACION),
        "es_tens": r.tiene_rol(u, r.TENS),
        "es_profesional": r.tiene_rol(u, r.PROFESIONAL),
    }

from . import roles as r

# clave, etiqueta, url, icono, prefijos que lo marcan como activo
MENU_TENS = [
    ("inicio", "Inicio", "/", "inicio", ()),
    ("citas", "Citas", "/citas/agendar/", "citas", ("/citas/",)),
    ("pacientes", "Pacientes", "/pacientes/", "pacientes", ("/pacientes/",)),
    ("documentos", "Documentos", "/documentos/", "documentos", ("/documentos/",)),
    ("espera", "Lista de espera", "/lista-espera/", "espera", ("/lista-espera/",)),
    ("profesionales_tens", "Profesionales", "/agenda/calendario/", "profesionales", ("/agenda/",)),
    ("asistencia", "Asistencia", "/asistencia/", "asistencia", ("/asistencia/",)),
]
MENU_ADMIN = [
    ("inicio", "Inicio", "/", "inicio", ()),
    ("profesionales", "Profesionales", "/profesionales/", "profesionales", ("/profesionales/", "/agenda/")),
    ("espera", "Lista de espera", "/lista-espera/", "espera", ("/lista-espera/",)),
    ("reportes", "Reportes", "/reportes/", "reportes", ("/reportes/",)),
    ("rep_pacientes", "Reporte de pacientes", "/reportes/?tab=pacientes", "pacientes", ("/reportes/pacientes/",)),
    ("documentos", "Documentos", "/documentos/", "documentos", ("/documentos/",)),
]

EXTRA_TENS = [("mensajes", "Avisos enviados", "/citas/mensajes/", "mensajes", ("/citas/mensajes/",))]
EXTRA_ADMIN = [("catalogo", "Especialidades y policlínicos", "/profesionales/catalogo/", "config", ("/profesionales/catalogo/",))]


def _menu(usuario):
    principal, extra = [], []
    if r.tiene_rol(usuario, r.TENS):
        principal += MENU_TENS
        extra += EXTRA_TENS
    if r.tiene_rol(usuario, r.ADMINISTRACION):
        principal += MENU_ADMIN
        extra += EXTRA_ADMIN
    vistos, items = set(), []
    for item in principal + [None] + extra:
        if item is None:
            if extra:
                items.append(None)
            continue
        if item[0] in vistos:
            continue
        vistos.add(item[0])
        items.append(item)
    return items


def _activo(items, path):
    mejor, largo = None, -1
    for it in items:
        if it is None:
            continue
        clave, _, url, _, prefijos = it
        if path == url and len(url) > largo:
            mejor, largo = clave, len(url)
        for p in prefijos:
            if path.startswith(p) and len(p) > largo:
                mejor, largo = clave, len(p)
    return mejor


def roles(request):
    """Flags de rol, menú lateral y contador de alertas para las plantillas."""
    u = getattr(request, "user", None)
    ctx = {
        "es_admin": r.tiene_rol(u, r.ADMINISTRACION),
        "es_tens": r.tiene_rol(u, r.TENS),
    }
    if u is None or not u.is_authenticated:
        return ctx
    items = _menu(u)
    ctx["menu"] = [
        None if it is None else {"clave": it[0], "etiqueta": it[1], "url": it[2], "icono": it[3]} for it in items
    ]
    ctx["menu_activo"] = _activo(items, request.path)
    if u.is_superuser:
        ctx["rol_visible"] = "Administrador del sistema"
    elif ctx["es_admin"]:
        ctx["rol_visible"] = "Administración"
    else:
        try:
            pol = r.policlinico_de(u)
        except Exception:  # pragma: no cover - TENS sin policlínico: la vista muestra el error
            pol = None
        ctx["policlinico_tens"] = pol
        ctx["rol_visible"] = f"{r.TENS} · {pol.nombre}" if pol else r.TENS
    try:
        from citas.services import contador_alertas

        ctx["alertas"] = contador_alertas(u)
    except Exception:  # pragma: no cover - nunca romper el layout por el contador
        ctx["alertas"] = 0
    return ctx

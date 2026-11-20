from django import template

from core import fechas
from pacientes.rut import formatear_rut

register = template.Library()


@register.filter
def fecha_corta(d):
    return fechas.fecha_corta(d) if d else ""


@register.filter
def fecha_larga(d):
    return fechas.fecha_larga(d) if d else ""


@register.filter
def fecha_larga_anio(d):
    return fechas.fecha_larga_anio(d) if d else ""


@register.filter
def rut(valor):
    return formatear_rut(valor) if valor else ""


@register.filter
def iniciales(nombre: str) -> str:
    partes = [p for p in (nombre or "").replace(".", " ").split() if p[0].isupper()]
    # Omite títulos (Dr., Dra., Kgo., Lic., Klgo., Ps.)
    titulos = {"Dr", "Dra", "Kgo", "Klgo", "Lic", "Ps", "Nut", "Flgo", "Enf"}
    partes = [p for p in partes if p not in titulos] or partes
    return "".join(p[0] for p in partes[:2]).upper()


@register.filter
def enmascarar_correo(correo: str) -> str:
    if not correo or "@" not in correo:
        return correo or ""
    usuario, dominio = correo.split("@", 1)
    return f"{usuario[0]}•••@{dominio}"


@register.filter
def enmascarar_celular(cel: str) -> str:
    digitos = "".join(ch for ch in (cel or "") if ch.isdigit())
    return f"+56 9 •••• {digitos[-4:]}" if len(digitos) >= 4 else cel


@register.filter
def porcentaje(parte, total):
    try:
        return round(100 * float(parte) / float(total)) if total else 0
    except (TypeError, ValueError):
        return 0


@register.filter
def get(dic, clave):
    try:
        return dic.get(clave)
    except AttributeError:
        return None


@register.inclusion_tag("includes/pill_cita.html")
def pill_cita(cita):
    return {"c": cita}


@register.filter
def primer_nombre(nombre: str) -> str:
    return (nombre or "").split(" ")[0]

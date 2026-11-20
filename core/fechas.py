"""Formato de fechas en español, independiente del idioma activo (se usa en mensajes y servicios)."""
from datetime import date, timedelta

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def fecha_larga(d: date) -> str:
    """'miércoles 21 de octubre'"""
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"


def fecha_larga_anio(d: date) -> str:
    """'Miércoles 21 de octubre de 2026'"""
    return f"{fecha_larga(d)} de {d.year}".capitalize()


def fecha_corta(d: date) -> str:
    """'Mié 21 oct'"""
    return f"{DIAS_CORTOS[d.weekday()]} {d.day} {MESES_CORTOS[d.month - 1]}"


def mes_anio(d: date) -> str:
    """'Octubre 2026'"""
    return f"{MESES[d.month - 1].capitalize()} {d.year}"


def lunes_de(d: date) -> date:
    return d - timedelta(days=d.weekday())


def rango_semana(lunes: date) -> str:
    """'19 al 23 oct 2026'"""
    viernes = lunes + timedelta(days=4)
    return f"{lunes.day} al {viernes.day} {MESES_CORTOS[viernes.month - 1]} {viernes.year}"

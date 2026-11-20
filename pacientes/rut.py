"""Utilidades para el RUT chileno (normalizar, validar dígito verificador, formatear)."""
import re

from django.core.exceptions import ValidationError


def calcular_dv(cuerpo: int | str) -> str:
    """Calcula el dígito verificador con el algoritmo módulo 11."""
    suma, factor = 0, 2
    for d in reversed(str(cuerpo)):
        suma += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    return {11: "0", 10: "K"}.get(resto, str(resto))


def normalizar_rut(valor: str) -> str:
    """'12.345.678-k' -> '12345678-K'. No valida el DV."""
    limpio = re.sub(r"[^0-9kK]", "", valor or "").upper()
    if len(limpio) < 2:
        return limpio
    return f"{limpio[:-1]}-{limpio[-1]}"


def es_rut_valido(valor: str) -> bool:
    rut = normalizar_rut(valor)
    if not re.fullmatch(r"\d{7,8}-[\dK]", rut):
        return False
    cuerpo, dv = rut.split("-")
    return calcular_dv(cuerpo) == dv


def validar_rut(valor: str) -> str:
    """Valida y devuelve el RUT normalizado. Lanza ValidationError si no es válido."""
    if not es_rut_valido(valor):
        raise ValidationError("El RUT ingresado no es válido (revise el dígito verificador).")
    return normalizar_rut(valor)


def formatear_rut(valor: str) -> str:
    """'12345678-K' -> '12.345.678-K'."""
    rut = normalizar_rut(valor)
    if "-" not in rut:
        return valor
    cuerpo, dv = rut.split("-")
    return f"{int(cuerpo):,}".replace(",", ".") + f"-{dv}"

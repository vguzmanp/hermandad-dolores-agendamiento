"""Excepciones de reglas de negocio, compartidas por todos los módulos."""


class ReglaNegocioError(Exception):
    """Violación de una regla de negocio (RN-xx). La vista la muestra como mensaje."""

    codigo = "RN"

    def __init__(self, mensaje: str, codigo: str | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        if codigo:
            self.codigo = codigo

    def __str__(self):
        return self.mensaje


class CupoNoDisponibleError(ReglaNegocioError):
    """RN-01 / RN-02: el cupo no existe, está bloqueado o ya tiene una cita normal."""

    codigo = "RN-02"


class SobrecupoNoPermitidoError(ReglaNegocioError):
    """RN-07: el sobrecupo solo es posible si la cita original está sin_respuesta."""

    codigo = "RN-07"


class TransicionEstadoInvalidaError(ReglaNegocioError):
    codigo = "ESTADO"

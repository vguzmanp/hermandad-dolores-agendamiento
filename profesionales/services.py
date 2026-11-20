from core import roles
from pacientes.rut import normalizar_rut

from .models import Profesional
from .repositories import ProfesionalRepository


class ProfesionalService:
    """Mantención de profesionales, especialidades y policlínicos (rol Administración)."""

    def __init__(self, repo: ProfesionalRepository | None = None):
        self.repo = repo or ProfesionalRepository()

    def guardar(self, obj, usuario):
        roles.exigir_rol(usuario, roles.ADMINISTRACION)
        if isinstance(obj, Profesional):
            obj.rut = normalizar_rut(obj.rut)
        return self.repo.guardar(obj)

"""Lógica de negocio del módulo Pacientes (RF-02, RN-03, RN-04, RN-05)."""
from django.db import transaction

from core import roles
from core.exceptions import ReglaNegocioError

from .models import AdultoResponsable, Paciente
from .repositories import PacienteRepository
from .rut import normalizar_rut


class PacienteService:
    def __init__(self, repo: PacienteRepository | None = None):
        self.repo = repo or PacienteRepository()

    def buscar_por_rut(self, rut: str) -> Paciente | None:
        """RF-02: buscar antes de registrar para no duplicar pacientes."""
        return self.repo.buscar_por_rut(rut)

    def buscar(self, texto: str = ""):
        return self.repo.buscar(texto)

    @transaction.atomic
    def guardar(
        self,
        paciente: Paciente,
        responsable: AdultoResponsable | None,
        usuario,
    ) -> Paciente:
        """Registra o actualiza un paciente y su adulto responsable (0..1)."""
        roles.exigir_rol(usuario, roles.TENS)
        paciente.rut = normalizar_rut(paciente.rut)
        if self.repo.existe_rut(paciente.rut, excluir_id=paciente.pk):
            raise ReglaNegocioError("Ya existe un paciente registrado con ese RUT.", "RF-02")
        if paciente.es_menor_de_edad:
            paciente.requiere_responsable = True
        if paciente.necesita_responsable and responsable is None:
            raise ReglaNegocioError("El paciente requiere un adulto responsable.", "RN-04")
        if paciente.pk is None:
            paciente.registrado_por = usuario
        self.repo.guardar(paciente)

        if paciente.necesita_responsable:
            responsable.paciente = paciente
            responsable.rut = normalizar_rut(responsable.rut)
            self.repo.guardar_responsable(responsable)
        else:
            # RN-04: solo cuando corresponde; si ya no corresponde se elimina.
            self.repo.eliminar_responsable(paciente)
        return paciente

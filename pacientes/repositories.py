"""Capa de acceso a datos del módulo Pacientes."""
from django.db.models import Q, QuerySet

from .models import AdultoResponsable, Paciente
from .rut import normalizar_rut


class PacienteRepository:
    def obtener(self, paciente_id: int) -> Paciente:
        return Paciente.objects.select_related("adulto_responsable").get(pk=paciente_id)

    def buscar_por_rut(self, rut: str) -> Paciente | None:
        return Paciente.objects.filter(rut=normalizar_rut(rut)).first()

    def existe_rut(self, rut: str, excluir_id: int | None = None) -> bool:
        qs = Paciente.objects.filter(rut=normalizar_rut(rut))
        if excluir_id:
            qs = qs.exclude(pk=excluir_id)
        return qs.exists()

    def buscar(self, texto: str = "") -> QuerySet[Paciente]:
        qs = Paciente.objects.select_related("adulto_responsable")
        texto = (texto or "").strip()
        if texto:
            rut = normalizar_rut(texto)
            filtro = Q(nombre__icontains=texto)
            if any(ch.isdigit() for ch in texto):
                filtro |= Q(rut__icontains=rut.replace("-", "")) | Q(rut__icontains=rut)
            qs = qs.filter(filtro)
        return qs.order_by("nombre")

    def guardar(self, paciente: Paciente) -> Paciente:
        paciente.save()
        return paciente

    def guardar_responsable(self, responsable: AdultoResponsable) -> AdultoResponsable:
        responsable.save()
        return responsable

    def eliminar_responsable(self, paciente: Paciente) -> None:
        AdultoResponsable.objects.filter(paciente=paciente).delete()

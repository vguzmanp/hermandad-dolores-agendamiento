"""Lógica de negocio del módulo Pacientes (RF-02, RN-03, RN-04, RN-05)."""
from django.conf import settings
from django.db import transaction

from core import roles
from core.exceptions import ReglaNegocioError

from .models import AdultoResponsable, DocumentoPaciente, OperacionDocumento, Paciente
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

    @transaction.atomic
    def registrar_web(self, paciente: Paciente, responsable: AdultoResponsable | None) -> Paciente:
        """Registro hecho por el propio paciente (o un familiar) desde el portal, sin cuenta."""
        paciente.rut = normalizar_rut(paciente.rut)
        if self.repo.existe_rut(paciente.rut):
            raise ReglaNegocioError("Ya existe un paciente con ese RUT.", "RF-02")
        if paciente.es_menor_de_edad:
            paciente.requiere_responsable = True
        if paciente.necesita_responsable and responsable is None:
            raise ReglaNegocioError("Debe indicar un adulto responsable.", "RN-04")
        self.repo.guardar(paciente)
        if paciente.necesita_responsable:
            responsable.paciente = paciente
            responsable.rut = normalizar_rut(responsable.rut)
            self.repo.guardar_responsable(responsable)
        return paciente


class DocumentoService:
    """Documentos del paciente (subida local) con historial de operaciones."""

    EXTENSIONES = (".pdf", ".jpg", ".jpeg", ".png")

    def _log(self, paciente, usuario, accion, detalle):
        OperacionDocumento.objects.create(paciente=paciente, usuario=usuario, accion=accion, detalle=detalle)

    def adjuntar(self, paciente: Paciente, tipo: str, archivo, usuario=None) -> DocumentoPaciente:
        """usuario=None: lo adjuntó el paciente desde la web."""
        if usuario is not None:
            roles.exigir_rol(usuario, roles.TENS, roles.ADMINISTRACION)
        nombre = archivo.name.rsplit("/", 1)[-1]
        if not nombre.lower().endswith(self.EXTENSIONES):
            raise ReglaNegocioError("Formato no permitido: use PDF, JPG o PNG.", "DOC")
        if archivo.size > settings.DOCUMENTO_MAX_MB * 1024 * 1024:
            raise ReglaNegocioError(f"El archivo supera los {settings.DOCUMENTO_MAX_MB} MB.", "DOC")
        with transaction.atomic():
            doc = DocumentoPaciente.objects.create(paciente=paciente, tipo=tipo, archivo=archivo, nombre=nombre,
                                                  tamano=archivo.size, subido_por=usuario)
            self._log(paciente, usuario, OperacionDocumento.Accion.ADJUNTO, doc.get_tipo_display())
            if tipo == DocumentoPaciente.Tipo.CESFAM and not paciente.inscrito_cesfam:
                paciente.inscrito_cesfam = True  # RN-05 resuelta con el comprobante
                paciente.save(update_fields=["inscrito_cesfam"])
        return doc

    def registrar_consulta(self, doc: DocumentoPaciente, usuario) -> None:
        roles.exigir_rol(usuario, roles.TENS, roles.ADMINISTRACION)
        self._log(doc.paciente, usuario, OperacionDocumento.Accion.CONSULTO, doc.nombre)

    def eliminar(self, doc: DocumentoPaciente, usuario) -> None:
        roles.exigir_rol(usuario, roles.TENS, roles.ADMINISTRACION)
        with transaction.atomic():
            self._log(doc.paciente, usuario, OperacionDocumento.Accion.ELIMINO, doc.nombre)
            nombre_archivo = doc.archivo.name if doc.archivo else None
            storage = doc.archivo.storage if doc.archivo else None
            doc.delete()
        if nombre_archivo:
            try:
                storage.delete(nombre_archivo)
            except OSError:  # p. ej. en Windows si el archivo sigue abierto; el registro ya se eliminó
                pass

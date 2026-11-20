from django.conf import settings
from django.db import models
from django.utils import timezone

from .rut import formatear_rut

EDAD_MAYORIA = 18


class Paciente(models.Model):
    class Sexo(models.TextChoices):
        FEMENINO = "F", "Femenino"
        MASCULINO = "M", "Masculino"
        OTRO = "O", "Otro / No informa"

    nombre = models.CharField("nombre completo", max_length=150)
    rut = models.CharField("RUT", max_length=12, unique=True, help_text="Formato 12345678-K")
    celular = models.CharField(max_length=20, help_text="Ej: +56912345678")
    correo = models.EmailField("correo electrónico", blank=True, help_text="Opcional (RN-03)")
    direccion = models.CharField("dirección", max_length=200)
    fecha_nacimiento = models.DateField("fecha de nacimiento")
    sexo = models.CharField(max_length=1, choices=Sexo.choices)
    nacionalidad = models.CharField(max_length=60, default="Chilena")
    # RN-05: inscripción en CESFAM (si falta, el sistema advierte)
    inscrito_cesfam = models.BooleanField("inscrito en CESFAM", default=False)
    cesfam = models.CharField("CESFAM", max_length=120, blank=True)
    # RN-04: adulto responsable 0..1 solo cuando corresponde
    requiere_responsable = models.BooleanField(
        "requiere adulto responsable",
        default=False,
        help_text="Se exige automáticamente para menores de 18 años; márquelo también en casos de dependencia.",
    )
    observaciones = models.TextField(blank=True)
    fecha_registro = models.DateTimeField(default=timezone.now, editable=False)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )

    class Meta:
        ordering = ["nombre"]
        verbose_name = "paciente"

    def __str__(self):
        return f"{self.nombre} ({self.rut_formateado})"

    @property
    def rut_formateado(self) -> str:
        return formatear_rut(self.rut)

    @property
    def edad(self) -> int:
        hoy = timezone.localdate()
        n = self.fecha_nacimiento
        return hoy.year - n.year - ((hoy.month, hoy.day) < (n.month, n.day))

    @property
    def es_menor_de_edad(self) -> bool:
        return self.edad < EDAD_MAYORIA

    @property
    def necesita_responsable(self) -> bool:
        """RN-04: corresponde tener adulto responsable."""
        return self.es_menor_de_edad or self.requiere_responsable

    @property
    def advertencias(self) -> list[str]:
        avisos = []
        if not self.inscrito_cesfam:
            avisos.append("RN-05: El paciente no registra inscripción en CESFAM. Solicite el comprobante.")
        if self.necesita_responsable and not hasattr(self, "adulto_responsable"):
            avisos.append("RN-04: El paciente requiere un adulto responsable y no tiene uno registrado.")
        return avisos


class AdultoResponsable(models.Model):
    paciente = models.OneToOneField(Paciente, on_delete=models.CASCADE, related_name="adulto_responsable")
    nombre = models.CharField("nombre completo", max_length=150)
    rut = models.CharField("RUT", max_length=12)
    parentesco = models.CharField(max_length=60, help_text="Ej: madre, padre, tutor legal")
    celular = models.CharField(max_length=20)
    correo = models.EmailField("correo electrónico", blank=True)

    class Meta:
        verbose_name = "adulto responsable"
        verbose_name_plural = "adultos responsables"

    def __str__(self):
        return f"{self.nombre} ({self.parentesco} de {self.paciente.nombre})"

    @property
    def rut_formateado(self) -> str:
        return formatear_rut(self.rut)


def ruta_documento(instancia, nombre):
    return f"documentos/{instancia.paciente.rut}/{nombre}"


class DocumentoPaciente(models.Model):
    class Tipo(models.TextChoices):
        FONASA = "fonasa", "Certificado de FONASA"
        CESFAM = "cesfam", "Inscripción al CESFAM"
        DERIVACION = "derivacion", "Orden de derivación"
        OTRO = "otro", "Otro certificado"

    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="documentos")
    tipo = models.CharField("tipo de documento", max_length=12, choices=Tipo.choices)
    archivo = models.FileField(upload_to=ruta_documento, blank=True,
                               help_text="Vacío solo en documentos de ejemplo de la demo.")
    nombre = models.CharField(max_length=150)
    tamano = models.PositiveIntegerField("tamaño (bytes)", default=0)
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+", help_text="Vacío si lo adjuntó el paciente desde la web.")
    subido_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-subido_en"]
        verbose_name = "documento del paciente"
        verbose_name_plural = "documentos del paciente"

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"

    @property
    def tamano_legible(self) -> str:
        if self.tamano >= 1024 * 1024:
            return f"{self.tamano / 1024 / 1024:.1f} MB".replace(".", ",")
        return f"{max(1, round(self.tamano / 1024))} KB"

    @property
    def es_imagen(self) -> bool:
        return self.nombre.lower().endswith((".jpg", ".jpeg", ".png"))


class OperacionDocumento(models.Model):
    """Historial: quién hizo qué y cuándo con los documentos del paciente."""

    class Accion(models.TextChoices):
        ADJUNTO = "adjunto", "Adjuntó documento"
        CONSULTO = "consulto", "Consultó documento"
        ELIMINO = "elimino", "Eliminó documento"

    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name="operaciones_documentos")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    accion = models.CharField(max_length=10, choices=Accion.choices)
    detalle = models.CharField(max_length=200)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-fecha", "-id"]

    @property
    def quien(self) -> str:
        if self.usuario is None:
            return "Paciente (web)"
        from core import roles
        if roles.tiene_rol(self.usuario, roles.TENS) and not self.usuario.is_superuser:
            return f"TENS/TONS · {self.usuario.get_full_name() or self.usuario.username}"
        return self.usuario.get_full_name() or self.usuario.username

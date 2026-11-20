"""
Repositorio de citas.

ICitaRepository define el contrato; CitaRepositoryPostgres lo implementa con el
ORM de Django. Las reglas RN-02 y RN-07 se verifican DENTRO de una transacción
(transaction.atomic) con select_for_update sobre el Cupo: dos TENS que intenten
agendar el mismo cupo a la vez quedan serializadas por el bloqueo de fila, y la
segunda ve la cita creada por la primera.

Además, la base de datos tiene restricciones únicas parciales (ver Cita.Meta)
que actúan como última línea de defensa.

Nota: en SQLite (uso temporal) select_for_update no hace nada, pero SQLite
serializa las escrituras a nivel de base de datos, por lo que la regla se
mantiene; el diseño está pensado para PostgreSQL.
"""
from abc import ABC, abstractmethod
from datetime import date

from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q, QuerySet
from django.utils import timezone

from agenda.models import Cupo
from core.exceptions import (
    CupoNoDisponibleError,
    ReglaNegocioError,
    SobrecupoNoPermitidoError,
    TransicionEstadoInvalidaError,
)
from pacientes.models import Paciente

from .models import Cita

Estado = Cita.Estado


class ICitaRepository(ABC):
    @abstractmethod
    def obtener(self, cita_id: int) -> Cita: ...

    @abstractmethod
    def crear_cita(self, cupo_id: int, paciente: Paciente, usuario, **datos) -> Cita:
        """Crea una cita normal. RN-01/RN-02: el cupo debe estar disponible."""

    @abstractmethod
    def crear_sobrecupo(self, cupo_id: int, paciente: Paciente, usuario, **datos) -> Cita:
        """RN-07: solo si la cita normal del cupo está 'sin_respuesta' y no hay otro sobrecupo."""

    @abstractmethod
    def cancelar(self, cita_id: int, usuario, motivo: str) -> Cita:
        """Cancela la cita y libera el cupo."""

    @abstractmethod
    def cambiar_estado(self, cita_id: int, nuevo: str, desde: tuple[str, ...], **campos) -> Cita: ...

    @abstractmethod
    def marcar_recordatorio(self, cita_id: int) -> None: ...

    @abstractmethod
    def cupos_libres(self, filtros: dict) -> QuerySet[Cupo]: ...

    @abstractmethod
    def cupos_para_sobrecupo(self, filtros: dict) -> QuerySet[Cupo]: ...

    @abstractmethod
    def siguientes_cupos_libres(self, cupo: Cupo, cantidad: int) -> list[Cupo]: ...

    @abstractmethod
    def listar(self, **filtros) -> QuerySet[Cita]: ...


class CitaRepositoryPostgres(ICitaRepository):
    # ----------------------------------------------------------------- lectura
    def _base(self) -> QuerySet[Cita]:
        return Cita.objects.select_related(
            "paciente", "paciente__adulto_responsable", "cupo__agenda__profesional__especialidad",
            "cupo__agenda__policlinico", "creada_por", "cita_original__paciente",
        )

    def obtener(self, cita_id: int) -> Cita:
        return self._base().get(pk=cita_id)

    def listar(self, fecha_desde=None, fecha_hasta=None, profesional=None, policlinico=None,
               estado=None, paciente=None) -> QuerySet[Cita]:
        qs = self._base()
        if fecha_desde:
            qs = qs.filter(cupo__fecha__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(cupo__fecha__lte=fecha_hasta)
        if profesional:
            qs = qs.filter(cupo__agenda__profesional=profesional)
        if policlinico:
            qs = qs.filter(cupo__agenda__policlinico=policlinico)
        if estado:
            qs = qs.filter(estado=estado)
        if paciente:
            qs = qs.filter(paciente=paciente)
        return qs

    # ----------------------------------------------------------- disponibilidad
    def _cupos_filtrables(self, filtros: dict) -> QuerySet[Cupo]:
        ahora = timezone.localtime()
        hoy = ahora.date()
        desde = max(filtros.get("desde") or hoy, hoy)
        hasta = filtros.get("hasta") or desde
        qs = (
            Cupo.objects.select_related("agenda__profesional__especialidad", "agenda__policlinico")
            .prefetch_related("citas__paciente")
            .filter(bloqueado=False, agenda__activa=True, fecha__range=(desde, hasta))
            .filter(Q(fecha__gt=hoy) | Q(hora_inicio__gte=ahora.time()))  # no ofrecer horas pasadas
        )
        if filtros.get("especialidad"):
            qs = qs.filter(agenda__profesional__especialidad=filtros["especialidad"])
        if filtros.get("profesional"):
            qs = qs.filter(agenda__profesional=filtros["profesional"])
        if filtros.get("policlinico"):
            qs = qs.filter(agenda__policlinico=filtros["policlinico"])
        return qs.order_by("fecha", "hora_inicio", "agenda__profesional__nombre")

    @staticmethod
    def _vigentes():
        return Cita.objects.filter(cupo=OuterRef("pk"), estado__in=Cita.VIGENTES)

    def cupos_libres(self, filtros: dict) -> QuerySet[Cupo]:
        """RN-01: cupos no bloqueados y sin cita normal vigente."""
        return self._cupos_filtrables(filtros).exclude(Exists(self._vigentes().filter(es_sobrecupo=False)))

    def cupos_para_sobrecupo(self, filtros: dict) -> QuerySet[Cupo]:
        """RN-07: cupos cuya cita normal está sin_respuesta y que aún no tienen sobrecupo."""
        return (
            self._cupos_filtrables(filtros)
            .filter(Exists(self._vigentes().filter(es_sobrecupo=False, estado=Estado.SIN_RESPUESTA)))
            .exclude(Exists(self._vigentes().filter(es_sobrecupo=True)))
        )

    def siguientes_cupos_libres(self, cupo: Cupo, cantidad: int) -> list[Cupo]:
        """
        RN-01 (todas las sesiones de una vez): siguientes cupos libres del mismo
        profesional y policlínico, a la misma hora, en fechas posteriores.
        """
        filtros = {"desde": cupo.fecha, "hasta": date.max}
        qs = self.cupos_libres(filtros).filter(
            agenda__profesional=cupo.agenda.profesional,
            agenda__policlinico=cupo.agenda.policlinico,
            hora_inicio=cupo.hora_inicio,
            fecha__gt=cupo.fecha,
        )
        return list(qs[:cantidad])

    # -------------------------------------------------------------- escritura
    @staticmethod
    def _bloquear_cupo(cupo_id: int) -> Cupo:
        """SELECT ... FOR UPDATE sobre el cupo: serializa los agendamientos concurrentes."""
        try:
            return Cupo.objects.select_for_update().get(pk=cupo_id)
        except Cupo.DoesNotExist:
            raise CupoNoDisponibleError("El cupo no existe.", "RN-01")

    @staticmethod
    def _validar_cupo_utilizable(cupo: Cupo) -> None:
        if cupo.bloqueado:
            raise CupoNoDisponibleError("El cupo está bloqueado por Administración.", "RN-01")
        ahora = timezone.localtime()
        if cupo.fecha < ahora.date() or (cupo.fecha == ahora.date() and cupo.hora_inicio < ahora.time()):
            raise CupoNoDisponibleError("No se puede agendar en un horario que ya pasó.", "RN-01")

    @staticmethod
    def _validar_paciente_sin_choque(paciente: Paciente, cupo: Cupo) -> None:
        choque = Cita.objects.filter(
            paciente=paciente, estado__in=Cita.VIGENTES, cupo__fecha=cupo.fecha,
            cupo__hora_inicio__lt=cupo.hora_fin, cupo__hora_fin__gt=cupo.hora_inicio,
        ).exists()
        if choque:
            raise ReglaNegocioError(
                f"El paciente ya tiene una cita vigente el {cupo.fecha:%d/%m/%Y} en ese horario.", "CHOQUE"
            )

    @staticmethod
    def _crear(**campos) -> Cita:
        try:
            with transaction.atomic():  # savepoint: un IntegrityError no rompe la transacción externa
                return Cita.objects.create(**campos)
        except IntegrityError:
            # Respaldo: la restricción única de la BD detectó una doble asignación.
            raise CupoNoDisponibleError("El cupo acaba de ser ocupado por otra cita.", "RN-02")

    def crear_cita(self, cupo_id: int, paciente: Paciente, usuario, **datos) -> Cita:
        with transaction.atomic():
            cupo = self._bloquear_cupo(cupo_id)
            self._validar_cupo_utilizable(cupo)
            # RN-02: dentro de la transacción y con el cupo bloqueado.
            if Cita.objects.filter(cupo=cupo, es_sobrecupo=False, estado__in=Cita.VIGENTES).exists():
                raise CupoNoDisponibleError("El cupo ya tiene una cita asignada.", "RN-02")
            self._validar_paciente_sin_choque(paciente, cupo)
            return self._crear(cupo=cupo, paciente=paciente, creada_por=usuario, es_sobrecupo=False, **datos)

    def crear_sobrecupo(self, cupo_id: int, paciente: Paciente, usuario, **datos) -> Cita:
        with transaction.atomic():
            cupo = self._bloquear_cupo(cupo_id)
            self._validar_cupo_utilizable(cupo)
            vigentes = list(Cita.objects.select_for_update().filter(cupo=cupo, estado__in=Cita.VIGENTES))
            original = next((c for c in vigentes if not c.es_sobrecupo), None)
            if original is None:
                raise SobrecupoNoPermitidoError("El cupo está libre: agende una cita normal, no un sobrecupo.")
            # RN-07: se verifica en la misma transacción que la cita original SIGA sin respuesta...
            if original.estado != Estado.SIN_RESPUESTA:
                raise SobrecupoNoPermitidoError(
                    f"Solo se puede agendar un sobrecupo si la cita del cupo está «sin respuesta» "
                    f"(estado actual: {original.get_estado_display().lower()})."
                )
            # ...y que no exista ya un sobrecupo (máximo 2 citas por cupo).
            if any(c.es_sobrecupo for c in vigentes):
                raise SobrecupoNoPermitidoError("El cupo ya tiene un sobrecupo (máximo 2 citas por cupo).")
            if original.paciente_id == paciente.pk:
                raise SobrecupoNoPermitidoError("El paciente ya es titular de la cita de este cupo.")
            self._validar_paciente_sin_choque(paciente, cupo)
            return self._crear(cupo=cupo, paciente=paciente, creada_por=usuario, es_sobrecupo=True,
                               cita_original=original, **datos)

    def cancelar(self, cita_id: int, usuario, motivo: str) -> Cita:
        """
        Cancela la cita: deja de ocupar el cupo, que queda libre por completo.
        Si se cancela la cita normal y existía un sobrecupo, el sobrecupo pasa a
        ser la cita normal del cupo (ese paciente sí asistirá).
        """
        with transaction.atomic():
            cupo_id = Cita.objects.values_list("cupo_id", flat=True).get(pk=cita_id)
            cupo = self._bloquear_cupo(cupo_id)
            cita = Cita.objects.select_for_update().get(pk=cita_id)
            if cita.estado == Estado.CANCELADA:
                raise TransicionEstadoInvalidaError("La cita ya estaba cancelada.")
            cita.estado = Estado.CANCELADA
            cita.cancelada_en = timezone.now()
            cita.cancelada_por = usuario
            cita.motivo_cancelacion = motivo
            cita.save()
            cita.sobrecupo_promovido = None
            if not cita.es_sobrecupo:
                sobre = (Cita.objects.select_for_update()
                         .filter(cupo=cupo, es_sobrecupo=True, estado__in=Cita.VIGENTES).first())
                if sobre:
                    sobre.es_sobrecupo = False
                    sobre.cita_original = None
                    sobre.save(update_fields=["es_sobrecupo", "cita_original"])
                    cita.sobrecupo_promovido = sobre
            return cita

    def cambiar_estado(self, cita_id: int, nuevo: str, desde: tuple[str, ...], **campos) -> Cita:
        with transaction.atomic():
            cita = Cita.objects.select_for_update().get(pk=cita_id)
            if cita.estado not in desde:
                raise TransicionEstadoInvalidaError(
                    f"No se puede pasar de «{cita.get_estado_display()}» a «{Estado(nuevo).label}»."
                )
            cita.estado = nuevo
            for k, v in campos.items():
                setattr(cita, k, v)
            cita.save()
            return cita

    def marcar_recordatorio(self, cita_id: int) -> None:
        Cita.objects.filter(pk=cita_id).update(recordatorio_enviado_en=timezone.now())

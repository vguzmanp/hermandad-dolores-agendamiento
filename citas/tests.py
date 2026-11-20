from datetime import date, time, timedelta

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from agenda.models import Agenda, Cupo
from agenda.services import AgendaService
from core import roles
from core.exceptions import CupoNoDisponibleError, ReglaNegocioError, SobrecupoNoPermitidoError
from pacientes.models import Paciente
from profesionales.models import Especialidad, Policlinico, Profesional

from .models import Cita, MensajeEnviado
from .repositories import CitaRepositoryPostgres
from .services import AgendamientoService, ConfirmacionService

Estado = Cita.Estado


def usuario(username, rol):
    u = User.objects.create_user(username, password="x")
    u.groups.add(Group.objects.get_or_create(name=rol)[0])
    return u


class CitasBase(TestCase):
    """Escenario: un profesional con un bloque semanal de 4 cupos, generado para 3 semanas desde mañana."""

    def setUp(self):
        self.tens = usuario("tens", roles.TENS)
        self.admin = usuario("adm", roles.ADMINISTRACION)
        self.esp = Especialidad.objects.create(nombre="Kinesiología", duracion_cupo_min=30,
                                               permite_agendar_todas_sesiones=True, sesiones_por_tratamiento=3)
        self.prof = Profesional.objects.create(nombre="Klgo. Prueba", rut="11111111-1", especialidad=self.esp)
        self.pol = Policlinico.objects.create(nombre="Policlínico Prueba")
        self.manana = timezone.localdate() + timedelta(days=1)
        self.agenda = Agenda.objects.create(
            profesional=self.prof, policlinico=self.pol, dia_semana=self.manana.weekday(),
            hora_inicio=time(9), hora_fin=time(11), vigente_desde=self.manana,
        )
        AgendaService().generar_cupos(self.agenda, self.manana, self.manana + timedelta(days=20), self.admin)
        self.cupo = Cupo.objects.filter(fecha=self.manana).order_by("hora_inicio").first()
        self.p1 = self.paciente("Paciente Uno", "11111111-1")
        self.p2 = self.paciente("Paciente Dos", "22222222-2")
        self.p3 = self.paciente("Paciente Tres", "33333333-3")
        self.servicio = AgendamientoService()
        self.confirmacion = ConfirmacionService()

    @staticmethod
    def paciente(nombre, rut):
        return Paciente.objects.create(nombre=nombre, rut=rut, celular="+56900000000", direccion="Calle 1",
                                       fecha_nacimiento=date(1990, 1, 1), sexo="F", inscrito_cesfam=True, cesfam="X")

    def agendar(self, paciente, cupo=None, **kw):
        return self.servicio.agendar(paciente, cupo or self.cupo, self.tens, **kw).citas[0]


class PruebasObligatoriasRN02RN07(CitasBase):
    """Pruebas obligatorias del enunciado."""

    def test_doble_asignacion_rechazada(self):
        self.agendar(self.p1)
        with self.assertRaises(CupoNoDisponibleError):
            self.agendar(self.p2)
        self.assertEqual(self.cupo.citas.filter(estado__in=Cita.VIGENTES).count(), 1)

    def test_sobrecupo_permitido_con_sin_respuesta(self):
        cita = self.agendar(self.p1)
        self.confirmacion.marcar_sin_respuesta(cita, self.tens)
        sobre = self.servicio.agendar_sobrecupo(self.p2, self.cupo, self.tens).citas[0]
        self.assertTrue(sobre.es_sobrecupo)
        self.assertEqual(sobre.cita_original, cita)
        self.assertEqual(self.cupo.citas.filter(estado__in=Cita.VIGENTES).count(), 2)

    def test_sobrecupo_rechazado_si_la_cita_esta_agendada(self):
        self.agendar(self.p1)
        with self.assertRaises(SobrecupoNoPermitidoError):
            self.servicio.agendar_sobrecupo(self.p2, self.cupo, self.tens)

    def test_sobrecupo_rechazado_si_la_cita_esta_confirmada(self):
        cita = self.agendar(self.p1)
        self.confirmacion.registrar_confirmacion(cita, self.tens)
        with self.assertRaises(SobrecupoNoPermitidoError):
            self.servicio.agendar_sobrecupo(self.p2, self.cupo, self.tens)

    def test_segundo_sobrecupo_rechazado(self):
        cita = self.agendar(self.p1)
        self.confirmacion.marcar_sin_respuesta(cita, self.tens)
        self.servicio.agendar_sobrecupo(self.p2, self.cupo, self.tens)
        with self.assertRaises(SobrecupoNoPermitidoError):
            self.servicio.agendar_sobrecupo(self.p3, self.cupo, self.tens)
        self.assertEqual(self.cupo.citas.filter(estado__in=Cita.VIGENTES).count(), 2)  # máximo 2 por cupo

    def test_cancelacion_libera_el_cupo(self):
        cita = self.agendar(self.p1)
        self.servicio.cancelar(cita, self.tens, "Paciente no puede asistir")
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Estado.CANCELADA)
        self.cupo.refresh_from_db()
        self.assertEqual(self.cupo.estado, Cupo.Estado.LIBRE)
        nueva = self.agendar(self.p2)  # el cupo vuelve a estar disponible
        self.assertEqual(nueva.cupo, self.cupo)


class ReglasAdicionales(CitasBase):
    def test_sobrecupo_rechazado_si_el_cupo_esta_libre(self):
        with self.assertRaises(SobrecupoNoPermitidoError):
            self.servicio.agendar_sobrecupo(self.p1, self.cupo, self.tens)

    def test_cancelar_sin_respuesta_promueve_al_sobrecupo(self):
        cita = self.agendar(self.p1)
        self.confirmacion.marcar_sin_respuesta(cita, self.tens)
        sobre = self.servicio.agendar_sobrecupo(self.p2, self.cupo, self.tens).citas[0]
        self.confirmacion.registrar_cancelacion(cita, self.tens)
        sobre.refresh_from_db()
        self.assertFalse(sobre.es_sobrecupo)
        with self.assertRaises(CupoNoDisponibleError):
            self.agendar(self.p3)

    def test_cancelar_sobrecupo_permite_otro_sobrecupo(self):
        cita = self.agendar(self.p1)
        self.confirmacion.marcar_sin_respuesta(cita, self.tens)
        sobre = self.servicio.agendar_sobrecupo(self.p2, self.cupo, self.tens).citas[0]
        self.servicio.cancelar(sobre, self.tens)
        self.servicio.agendar_sobrecupo(self.p3, self.cupo, self.tens)

    def test_cupo_bloqueado_no_se_agenda(self):
        AgendaService().bloquear_cupo(self.cupo, "Licencia", self.admin)
        self.cupo.refresh_from_db()
        with self.assertRaises(CupoNoDisponibleError):
            self.agendar(self.p1)

    def test_paciente_no_puede_tener_dos_citas_a_la_misma_hora(self):
        otra_agenda = Agenda.objects.create(
            profesional=Profesional.objects.create(nombre="Otro", rut="22222222-2", especialidad=self.esp),
            policlinico=self.pol, dia_semana=self.manana.weekday(), hora_inicio=time(9), hora_fin=time(10),
            vigente_desde=self.manana,
        )
        AgendaService().generar_cupos(otra_agenda, self.manana, self.manana, self.admin)
        self.agendar(self.p1)
        with self.assertRaises(ReglaNegocioError):
            self.agendar(self.p1, cupo=otra_agenda.cupos.get(hora_inicio=time(9)))

    def test_solo_tens_registra_citas(self):
        with self.assertRaises(PermissionDenied):
            self.servicio.agendar(self.p1, self.cupo, self.admin)

    def test_restriccion_bd_impide_doble_cita_normal(self):
        """Respaldo en la base de datos aunque se salte el repositorio."""
        Cita.objects.create(cupo=self.cupo, paciente=self.p1, creada_por=self.tens)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cita.objects.create(cupo=self.cupo, paciente=self.p2, creada_por=self.tens)

    def test_dias_aviso_por_defecto_es_2(self):
        self.assertEqual(self.agendar(self.p1).dias_aviso, 2)

    def test_agendar_todas_las_sesiones_de_una_vez(self):
        r = self.servicio.agendar(self.p1, self.cupo, self.tens, sesiones=3)
        self.assertEqual(len(r.citas), 3)
        self.assertEqual([c.numero_sesion for c in r.citas], [1, 2, 3])
        self.assertEqual(len({c.grupo_sesiones for c in r.citas}), 1)
        self.assertEqual([c.cupo.fecha for c in r.citas],
                         [self.manana, self.manana + timedelta(days=7), self.manana + timedelta(days=14)])

    def test_sesiones_todo_o_nada(self):
        ocupado = Cupo.objects.get(fecha=self.manana + timedelta(days=14), hora_inicio=self.cupo.hora_inicio)
        self.agendar(self.p2, cupo=ocupado)
        with self.assertRaises(ReglaNegocioError):
            self.servicio.agendar(self.p1, self.cupo, self.tens, sesiones=3)
        self.assertFalse(Cita.objects.filter(paciente=self.p1).exists())

    def test_especialidad_sin_sesiones_multiples(self):
        self.esp.permite_agendar_todas_sesiones = False
        self.esp.save()
        with self.assertRaises(ReglaNegocioError):
            self.servicio.agendar(self.p1, self.cupo, self.tens, sesiones=2)

    def test_disponibilidad(self):
        cita = self.agendar(self.p1)
        disp = self.servicio.disponibilidad(self.manana, profesional=self.prof)
        self.assertNotIn(self.cupo, disp["libres"])
        self.assertEqual(len(disp["libres"]), 3)
        self.assertEqual(disp["sobrecupo"], [])
        self.confirmacion.marcar_sin_respuesta(cita, self.tens)
        self.assertEqual(self.servicio.disponibilidad(self.manana)["sobrecupo"], [self.cupo])

    def test_flujo_confirmacion_y_mensajes(self):
        cita = self.agendar(self.p1, cupo=self.cupo)
        hoy_aviso = cita.fecha_aviso
        self.assertIn(cita, self.confirmacion.recordatorios_pendientes(hoy=max(hoy_aviso, timezone.localdate())))
        self.confirmacion.enviar_recordatorio(cita, self.tens)
        self.confirmacion.registrar_confirmacion(cita, self.tens)
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Estado.CONFIRMADA)
        tipos = list(MensajeEnviado.objects.filter(cita=cita).values_list("tipo", flat=True))
        self.assertCountEqual(tipos, ["agendamiento", "recordatorio", "confirmacion"])

    def test_repositorio_implementa_interfaz(self):
        from .repositories import ICitaRepository
        self.assertIsInstance(CitaRepositoryPostgres(), ICitaRepository)


class ReagendarTests(CitasBase):
    def test_reagendar_libera_la_hora_anterior(self):
        cita = self.agendar(self.p1)
        otro = Cupo.objects.filter(fecha=self.manana).exclude(pk=self.cupo.pk).first()
        nueva = self.servicio.reagendar(cita, otro, self.tens)
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Estado.CANCELADA)
        self.assertEqual(nueva.cupo, otro)
        self.agendar(self.p2)  # la hora original quedó libre

    def test_reagendar_a_hora_ocupada_no_cambia_nada(self):
        cita = self.agendar(self.p1)
        otro = Cupo.objects.filter(fecha=self.manana).exclude(pk=self.cupo.pk).first()
        self.agendar(self.p2, cupo=otro)
        with self.assertRaises(CupoNoDisponibleError):
            self.servicio.reagendar(cita, otro, self.tens)
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Estado.AGENDADA)  # rollback: la cita original sigue vigente

    def test_aviso_falla_con_celular_invalido(self):
        self.p1.celular = "+56 2 2345 6789"
        self.p1.save()
        cita = self.agendar(self.p1)
        self.assertFalse(self.confirmacion.enviar_recordatorio(cita, self.tens))
        cita.refresh_from_db()
        self.assertEqual(cita.estado_aviso, "fallido")


class CitasVistasTests(CitasBase):
    def url_agendar(self):
        return (f"{reverse('citas:agendar')}?paciente={self.p1.pk}&especialidad={self.esp.pk}"
                f"&profesional={self.prof.pk}&fecha={self.manana.isoformat()}")

    def test_flujo_completo_por_interfaz(self):
        self.client.force_login(self.tens)
        r = self.client.get(self.url_agendar())
        self.assertContains(r, self.cupo.hora_inicio.strftime("%H:%M"))
        datos = {"paciente": self.p1.pk, "especialidad": self.esp.pk, "profesional": self.prof.pk,
                 "canal": "telefono", "cupo": self.cupo.pk, "tipo": "normal"}
        self.client.post(reverse("citas:agendar"), datos)
        cita = Cita.objects.get(paciente=self.p1)
        self.assertEqual(cita.canal, "telefono")
        # doble asignación por interfaz: rechazada con mensaje
        r = self.client.post(reverse("citas:agendar"), {**datos, "paciente": self.p2.pk}, follow=True)
        self.assertContains(r, "RN-02")
        # «Registrar respuesta: sin respuesta» y luego sobrecupo
        self.client.post(reverse("citas:accion", args=[cita.pk, "respuesta"]), {"respuesta": "sin_respuesta"})
        self.client.post(reverse("citas:agendar"), {**datos, "paciente": self.p2.pk, "tipo": "sobrecupo"})
        self.assertEqual(Cita.objects.filter(cupo=self.cupo, es_sobrecupo=True).count(), 1)
        for url in [reverse("citas:lista"), reverse("citas:mensajes"), reverse("citas:detalle", args=[cita.pk]),
                    reverse("home"), self.url_agendar()]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_reagendar_por_interfaz(self):
        cita = self.agendar(self.p1)
        otro = Cupo.objects.filter(fecha=self.manana).exclude(pk=self.cupo.pk).first()
        self.client.force_login(self.tens)
        self.client.post(reverse("citas:agendar"), {"paciente": self.p1.pk, "cupo": otro.pk, "tipo": "normal",
                                                    "reagendar": cita.pk})
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Estado.CANCELADA)
        self.assertTrue(Cita.objects.filter(paciente=self.p1, cupo=otro, estado=Estado.AGENDADA).exists())

    def test_anotar_en_lista_de_espera(self):
        from lista_espera.models import SolicitudEspera
        self.client.force_login(self.tens)
        self.client.post(reverse("citas:agendar"), {"accion": "espera", "paciente": self.p1.pk,
                                                    "especialidad": self.esp.pk, "profesional": self.prof.pk})
        self.assertTrue(SolicitudEspera.objects.filter(paciente=self.p1, estado="en_espera").exists())

    def test_administracion_no_agenda(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("citas:agendar")).status_code, 403)

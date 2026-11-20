from datetime import time, timedelta

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import roles
from core.exceptions import ReglaNegocioError
from profesionales.models import Especialidad, Policlinico, Profesional

from .models import Agenda, Cupo
from .services import AgendaService


def usuario(username, rol):
    u = User.objects.create_user(username, password="x")
    u.groups.add(Group.objects.get_or_create(name=rol)[0])
    return u


class AgendaBase(TestCase):
    def setUp(self):
        self.admin = usuario("adm", roles.ADMINISTRACION)
        self.tens = usuario("tens", roles.TENS)
        esp = Especialidad.objects.create(nombre="Medicina General", duracion_cupo_min=30)
        self.prof = Profesional.objects.create(nombre="Dra. Prueba", rut="11111111-1", especialidad=esp)
        self.pol = Policlinico.objects.create(nombre="Policlínico Prueba")
        self.hoy = timezone.localdate()
        self.servicio = AgendaService()

    def agenda(self, dia=None, hi="09:00", hf="11:00", **kw):
        a = Agenda(profesional=self.prof, policlinico=self.pol,
                   dia_semana=self.hoy.weekday() if dia is None else dia,
                   hora_inicio=time.fromisoformat(hi), hora_fin=time.fromisoformat(hf),
                   vigente_desde=self.hoy, **kw)
        return self.servicio.guardar_agenda(a, self.admin)


class AgendaServiceTests(AgendaBase):
    def test_genera_cupos_desde_bloque_semanal(self):
        a = self.agenda()  # 09:00-11:00 / 30 min = 4 cupos por semana
        n = self.servicio.generar_cupos(a, self.hoy, self.hoy + timedelta(days=20), self.admin)
        self.assertEqual(n, 3 * 4)  # hoy, +7 y +14
        self.assertTrue(all(c.fecha.weekday() == a.dia_semana for c in Cupo.objects.all()))

    def test_generar_no_duplica(self):
        a = self.agenda()
        self.servicio.generar_cupos(a, self.hoy, self.hoy + timedelta(days=13), self.admin)
        self.assertEqual(self.servicio.generar_cupos(a, self.hoy, self.hoy + timedelta(days=13), self.admin), 0)

    def test_duracion_propia_de_la_agenda(self):
        a = self.agenda(duracion_cupo_min=60)
        self.assertEqual(self.servicio.generar_cupos(a, self.hoy, self.hoy, self.admin), 2)

    def test_bloques_solapados_rechazados(self):
        self.agenda()
        with self.assertRaises(ReglaNegocioError):
            self.agenda(hi="10:30", hf="12:00")
        self.agenda(hi="11:00", hf="12:00")  # contiguo: permitido

    def test_bloquear_y_liberar_cupo(self):
        a = self.agenda()
        self.servicio.generar_cupos(a, self.hoy, self.hoy, self.admin)
        cupo = Cupo.objects.first()
        self.servicio.bloquear_cupo(cupo, "Licencia", self.admin)
        cupo.refresh_from_db()
        self.assertEqual(cupo.estado, Cupo.Estado.BLOQUEADO)
        self.servicio.liberar_cupo(cupo, self.admin)
        cupo.refresh_from_db()
        self.assertEqual(cupo.estado, Cupo.Estado.LIBRE)

    def test_bloquear_dia(self):
        a = self.agenda()
        self.servicio.generar_cupos(a, self.hoy, self.hoy, self.admin)
        self.assertEqual(self.servicio.bloquear_dia(a, self.hoy, "Feriado", self.admin), (4, 0))

    def test_solo_administracion_gestiona_agendas(self):
        a = self.agenda()
        with self.assertRaises(PermissionDenied):
            self.servicio.generar_cupos(a, self.hoy, self.hoy, self.tens)


class AgendaVistasTests(AgendaBase):
    def test_paginas_de_agenda(self):
        a = self.agenda()
        self.client.force_login(self.admin)
        for url in [reverse("agenda:lista"), reverse("agenda:crear"), reverse("agenda:detalle", args=[a.pk]),
                    reverse("profesionales:lista"), reverse("profesionales:especialidades"),
                    reverse("profesionales:policlinicos")]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_crear_agenda_y_generar_por_formulario(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("agenda:crear"), {
            "profesional": self.prof.pk, "policlinico": self.pol.pk, "dia_semana": self.hoy.weekday(),
            "hora_inicio": "15:00", "hora_fin": "16:00", "vigente_desde": self.hoy.isoformat(),
            "activa": "on", "generar_semanas": 2,
        })
        a = Agenda.objects.get()
        self.assertRedirects(resp, reverse("agenda:detalle", args=[a.pk]))
        self.assertEqual(a.cupos.count(), 2 * 3)  # hoy, +7, +14

    def test_tens_no_gestiona_agendas(self):
        self.client.force_login(self.tens)
        self.assertEqual(self.client.get(reverse("agenda:lista")).status_code, 403)

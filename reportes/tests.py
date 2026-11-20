from django.contrib.auth.models import Group, User
from django.urls import reverse
from django.utils import timezone

from asistencia.models import Asistencia
from citas.models import Cita
from citas.tests import CitasBase
from core import roles

from .services import ReporteService, construir_filtros


class ReportesTests(CitasBase):
    def setUp(self):
        super().setUp()
        hoy = timezone.localdate()
        cupos = list(self.agenda.cupos.order_by("fecha", "hora_inicio")[:3])
        for cupo in cupos:
            cupo.fecha = hoy
            cupo.save()
        for cupo, p, asistio in zip(cupos, (self.p1, self.p2, self.p3), (True, True, False)):
            c = Cita.objects.create(cupo=cupo, paciente=p, estado="confirmada", creada_por=self.tens)
            Asistencia.objects.create(cita=c, asistio=asistio, registrada_por=self.tens)

    def test_demanda_e_inasistencia(self):
        d = ReporteService().demanda(construir_filtros("1m"))
        self.assertEqual((d["pedidas"], d["atenciones"]), (3, 2))
        self.assertAlmostEqual(d["inasistencia"], 33.3)
        self.assertEqual(d["por_profesional"][0]["nombre"], self.prof.nombre)
        self.assertEqual(d["por_policlinico"][0]["nombre"], self.pol.nombre)

    def test_caracterizacion(self):
        c = ReporteService().caracterizacion(construir_filtros("1m"))
        self.assertEqual(c["atendidos"], 2)
        self.assertEqual(c["mujeres"], 100)

    def test_vistas_y_csv(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("reportes:inicio")).status_code, 200)
        self.assertContains(self.client.get(reverse("reportes:inicio"), {"tab": "demanda"}), self.prof.nombre)
        r = self.client.get(reverse("reportes:csv"))
        self.assertIn(self.prof.nombre, r.content.decode("utf-8"))

    def test_profesional_ve_solo_lo_suyo(self):
        u = User.objects.create_user("profe", password="x")
        u.groups.add(Group.objects.get_or_create(name=roles.PROFESIONAL)[0])
        self.client.force_login(u)  # no está asociado al profesional del escenario
        r = self.client.get(reverse("reportes:inicio"))
        self.assertEqual(r.status_code, 403)
        self.assertNotContains(r, self.prof.nombre, status_code=403)
        self.prof.usuario = u
        self.prof.save()
        self.assertContains(self.client.get(reverse("reportes:inicio")), self.prof.nombre)
        self.client.force_login(self.tens)
        self.assertEqual(self.client.get(reverse("reportes:inicio")).status_code, 403)

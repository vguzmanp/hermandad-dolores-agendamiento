from datetime import date

from django.urls import reverse
from django.utils import timezone

from asistencia.models import Asistencia
from citas.models import Cita
from citas.tests import CitasBase
from lista_espera.services import ListaEsperaService

from .services import ReporteService, construir_filtros


class ReportesTests(CitasBase):
    def setUp(self):
        super().setUp()
        hoy = timezone.localdate()
        cupos = list(self.agenda.cupos.order_by("fecha", "hora_inicio")[:3])
        for cupo in cupos:
            cupo.fecha = hoy
            cupo.save()
        self.citas = []
        for cupo, p, asistio in zip(cupos, (self.p1, self.p2, self.p3), (True, True, False)):
            c = Cita.objects.create(cupo=cupo, paciente=p, estado="confirmada", creada_por=self.tens)
            Asistencia.objects.create(cita=c, asistio=asistio, registrada_por=self.tens)
            self.citas.append(c)
        self.s = ReporteService()

    def f(self, **datos):
        return construir_filtros({"periodo": "1m", **datos})

    def test_demanda_e_inasistencia(self):
        d = self.s.demanda(self.f())
        self.assertEqual((d["pedidas"], d["atenciones"]), (3, 2))
        self.assertAlmostEqual(d["inasistencia"], 33.3)
        self.assertEqual(d["por_profesional"][0]["nombre"], self.prof.nombre)
        self.assertEqual(d["por_policlinico"][0]["nombre"], self.pol.nombre)
        self.assertEqual(d["por_especialidad"][0]["nombre"], self.esp.nombre)

    def test_caracterizacion(self):
        c = self.s.caracterizacion(self.f())
        self.assertEqual((c["pacientes"], c["atendidos"]), (3, 2))
        self.assertEqual(c["mujeres"], 100)

    def test_filtros_combinables(self):
        self.p3.sexo = "M"
        self.p3.save()
        self.assertEqual(self.s.demanda(self.f(sexo="M"))["pedidas"], 1)
        self.assertEqual(self.s.demanda(self.f(asistencia="no_asistio"))["pedidas"], 1)
        self.assertEqual(self.s.demanda(self.f(asistencia="asistio", sexo="M"))["pedidas"], 0)
        self.assertEqual(self.s.demanda(self.f(edad="30-59"))["pedidas"], 3)  # nacidos en 1990
        self.assertEqual(self.s.demanda(self.f(edad="0-14"))["pedidas"], 0)
        self.assertEqual(self.s.demanda(self.f(estado="cancelada"))["pedidas"], 0)
        self.assertEqual(self.s.demanda(self.f(policlinico=self.pol, especialidad=self.esp))["pedidas"], 3)
        rango = construir_filtros({"periodo": "rango", "desde": date(2000, 1, 1), "hasta": date(2000, 12, 31)})
        self.assertEqual(self.s.demanda(rango)["pedidas"], 0)

    def test_reporte_de_pacientes(self):
        filas = list(self.s.pacientes(self.f()))
        self.assertEqual(len(filas), 3)
        p3 = next(p for p in filas if p.pk == self.p3.pk)
        self.assertEqual((p3.n_citas, p3.n_asistidas, p3.n_inasistencias), (1, 0, 1))
        con_inas = list(self.s.pacientes(self.f(con_inasistencias="si")))
        self.assertEqual([p.pk for p in con_inas], [self.p3.pk])
        self.assertEqual(len(self.s.pacientes(self.f(q="Uno"))), 1)
        ListaEsperaService().anotar(self.p2, self.esp, self.pol)
        self.assertEqual([p.pk for p in self.s.pacientes(self.f(en_espera="si"))], [self.p2.pk])

    def test_historial_del_paciente(self):
        h = self.s.historial(self.p3, construir_filtros({"periodo": "todo"}))
        self.assertEqual(h["kpi"]["total"], 1)
        self.assertEqual(h["kpi"]["inasistencias"], 1)

    def test_vistas_y_csv(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("reportes:inicio")).status_code, 200)
        self.assertContains(self.client.get(reverse("reportes:inicio"), {"tab": "demanda"}), self.prof.nombre)
        r = self.client.get(reverse("reportes:inicio"), {"tab": "pacientes", "sexo": "F", "edad": "30-59"})
        self.assertContains(r, self.p1.nombre)
        self.assertContains(self.client.get(reverse("reportes:paciente", args=[self.p1.pk])), "Historial de citas")
        self.assertIn(self.prof.nombre, self.client.get(reverse("reportes:csv")).content.decode("utf-8"))
        self.assertIn(self.p1.nombre, self.client.get(reverse("reportes:csv_pacientes")).content.decode("utf-8"))
        self.assertIn(self.esp.nombre,
                      self.client.get(reverse("reportes:csv_paciente", args=[self.p1.pk])).content.decode("utf-8"))

    def test_solo_administracion(self):
        self.client.force_login(self.tens)
        self.assertEqual(self.client.get(reverse("reportes:inicio")).status_code, 403)
        self.assertEqual(self.client.get(reverse("reportes:paciente", args=[self.p1.pk])).status_code, 403)

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from citas.models import Cita
from citas.tests import CitasBase
from core.exceptions import ReglaNegocioError

from .models import Asistencia
from .services import AsistenciaService


class AsistenciaTests(CitasBase):
    def cita_de_hoy(self, estado="confirmada"):
        cupo = self.cupo
        cupo.fecha = timezone.localdate()
        cupo.save()
        return Cita.objects.create(cupo=cupo, paciente=self.p1, estado=estado, creada_por=self.tens)

    def test_registrar_y_corregir_asistencia(self):
        cita = self.cita_de_hoy()
        s = AsistenciaService()
        s.registrar(cita, True, self.tens)
        s.registrar(cita, False, self.tens)  # si se marcó mal, se corrige
        self.assertFalse(Asistencia.objects.get(cita=cita).asistio)

    def test_cita_cancelada_no_registra_asistencia(self):
        cita = self.cita_de_hoy("cancelada")
        with self.assertRaises(ReglaNegocioError):
            AsistenciaService().registrar(cita, True, self.tens)

    def test_cita_futura_no_registra_asistencia(self):
        cita = self.agendar(self.p1)
        with self.assertRaises(ReglaNegocioError):
            AsistenciaService().registrar(cita, True, self.tens)

    def test_por_interfaz(self):
        cita = self.cita_de_hoy()
        self.client.force_login(self.tens)
        self.assertContains(self.client.get(reverse("asistencia:lista")), self.p1.nombre)
        self.client.post(reverse("asistencia:registrar", args=[cita.pk]), {"asistio": "1"})
        self.assertTrue(Asistencia.objects.get(cita=cita).asistio)
        r = self.client.get(reverse("asistencia:lista"), {"fecha": (timezone.localdate() + timedelta(days=1)).isoformat()})
        self.assertEqual(r.status_code, 200)

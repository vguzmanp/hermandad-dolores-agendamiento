from django.core.exceptions import PermissionDenied
from django.urls import reverse

from citas.tests import CitasBase

from .models import SolicitudEspera
from .services import ListaEsperaService


class ListaEsperaTests(CitasBase):
    def setUp(self):
        super().setUp()
        self.s = ListaEsperaService()
        self.a = self.s.anotar(self.p1, self.esp)
        self.b = self.s.anotar(self.p2, self.esp)
        self.c = self.s.anotar(self.p3, self.esp)

    def orden(self):
        return list(SolicitudEspera.objects.order_by("orden").values_list("paciente__nombre", flat=True))

    def test_orden_de_llegada_rn06(self):
        self.assertEqual(self.orden(), ["Paciente Uno", "Paciente Dos", "Paciente Tres"])

    def test_no_duplica_al_mismo_paciente(self):
        self.assertEqual(self.s.anotar(self.p1, self.esp).pk, self.a.pk)

    def test_tens_sube_a_un_paciente(self):
        self.s.subir(self.c, self.tens)
        self.assertEqual(self.orden(), ["Paciente Uno", "Paciente Tres", "Paciente Dos"])
        with self.assertRaises(PermissionDenied):
            self.s.subir(self.c, self.admin)

    def test_al_agendar_queda_como_agendado(self):
        self.agendar(self.p1)
        self.a.refresh_from_db()
        self.assertEqual(self.a.estado, SolicitudEspera.Estado.AGENDADO)

    def test_vistas(self):
        self.client.force_login(self.tens)
        self.assertContains(self.client.get(reverse("lista_espera:lista"), {"sel": self.b.pk}), "Actualizar estado")
        self.client.post(reverse("lista_espera:gestionar", args=[self.b.pk]),
                         {"estado": "contactado", "resultado_contacto": "no_contesta", "nota": "Llamar en la tarde"})
        self.b.refresh_from_db()
        self.assertEqual((self.b.estado, self.b.nota), ("contactado", "Llamar en la tarde"))
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("lista_espera:lista")), "Solo consulta")
        self.client.post(reverse("lista_espera:gestionar", args=[self.b.pk]), {"accion": "subir"})
        self.b.refresh_from_db()
        self.assertEqual(self.b.orden, 2)  # Administración no puede reordenar

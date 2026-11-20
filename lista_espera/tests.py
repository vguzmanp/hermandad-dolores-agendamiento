from datetime import time

from django.core.exceptions import PermissionDenied
from django.urls import reverse

from agenda.models import Agenda
from citas.tests import CitasBase, usuario
from core import roles
from core.exceptions import ReglaNegocioError
from profesionales.models import Especialidad, Policlinico, Profesional

from .models import SolicitudEspera
from .services import ListaEsperaService, posiciones


class ListaEsperaTests(CitasBase):
    def setUp(self):
        super().setUp()
        self.s = ListaEsperaService()
        self.a = self.s.anotar(self.p1, self.esp, self.pol)
        self.b = self.s.anotar(self.p2, self.esp, self.pol)
        self.c = self.s.anotar(self.p3, self.esp, self.pol)

    def orden(self):
        return list(SolicitudEspera.objects.order_by("orden").values_list("paciente__nombre", flat=True))

    def test_orden_de_llegada(self):
        self.assertEqual(self.orden(), ["Paciente Uno", "Paciente Dos", "Paciente Tres"])

    def test_no_duplica_al_mismo_paciente(self):
        self.assertEqual(self.s.anotar(self.p1, self.esp, self.pol).pk, self.a.pk)

    def test_la_lista_es_de_especialidad_y_policlinico_no_de_profesional(self):
        campos = {f.name for f in SolicitudEspera._meta.get_fields()}
        self.assertNotIn("profesional", campos)
        with self.assertRaises(ReglaNegocioError):
            self.s.anotar(self.p1, self.esp, None)

    def test_no_se_anota_en_un_policlinico_sin_la_especialidad(self):
        otro = Policlinico.objects.create(nombre="Policlínico Sin Kine")
        with self.assertRaises(ReglaNegocioError):
            self.s.anotar(self.p1, self.esp, otro)

    def test_tens_sube_a_un_paciente(self):
        self.s.subir(self.c, self.tens)
        self.assertEqual(self.orden(), ["Paciente Uno", "Paciente Tres", "Paciente Dos"])
        with self.assertRaises(PermissionDenied):
            self.s.subir(self.c, self.admin)

    def test_subir_solo_dentro_de_la_misma_lista(self):
        # otra lista (otra especialidad en el mismo policlínico) no se mezcla con la de Kinesiología
        nutri = Especialidad.objects.create(nombre="Nutrición")
        prof = Profesional.objects.create(nombre="Nut. Prueba", rut="12312312-3", especialidad=nutri)
        Agenda.objects.create(profesional=prof, policlinico=self.pol, dia_semana=0, hora_inicio=time(9),
                              hora_fin=time(10), vigente_desde=self.manana)
        d = self.s.anotar(self.p1, nutri, self.pol)
        self.assertFalse(self.s.subir(d, self.tens))  # es el primero de su lista
        self.assertEqual(posiciones(SolicitudEspera.objects.all())[d.pk], 1)
        self.assertEqual(posiciones(SolicitudEspera.objects.all())[self.c.pk], 3)

    def test_tens_de_otro_policlinico_no_gestiona(self):
        otra_tens = usuario("otra", roles.TENS)
        Policlinico.objects.create(nombre="Policlínico Otro", usuario_tens=otra_tens)
        with self.assertRaises(PermissionDenied):
            self.s.subir(self.c, otra_tens)
        self.client.force_login(otra_tens)
        self.assertNotContains(self.client.get(reverse("lista_espera:lista")), "Paciente Uno")

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

    def test_tens_anota_desde_agendar_sin_profesional(self):
        SolicitudEspera.objects.all().delete()
        self.client.force_login(self.tens)
        self.client.post(reverse("citas:agendar"), {"accion": "espera", "paciente": self.p1.pk,
                                                    "especialidad": self.esp.pk, "profesional": self.prof.pk})
        s = SolicitudEspera.objects.get()
        self.assertEqual((s.paciente, s.especialidad, s.policlinico), (self.p1, self.esp, self.pol))

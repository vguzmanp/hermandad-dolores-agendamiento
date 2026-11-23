"""Portal del paciente (sin cuenta): reservar, lista de espera y responder el aviso."""
from django.urls import reverse

from agenda.models import Cupo
from citas.models import Cita, MensajeEnviado
from citas.tests import CitasBase
from lista_espera.models import SolicitudEspera
from pacientes.models import Paciente


class PortalReservaTests(CitasBase):
    def test_reserva_completa_paciente_existente(self):
        r = self.client.get(reverse("portal:horas"), {"esp": self.esp.pk, "pol": self.pol.pk})
        self.assertContains(r, self.prof.nombre)
        self.client.post(reverse("portal:horas"), {"esp": self.esp.pk, "pol": self.pol.pk, "cupo": self.cupo.pk})
        r = self.client.post(reverse("portal:datos"), {"paso": "rut", "rut": self.p1.rut})
        self.assertRedirects(r, reverse("portal:confirmar"))
        r = self.client.post(reverse("portal:confirmar"))
        cita = Cita.objects.get(paciente=self.p1)
        self.assertRedirects(r, reverse("portal:listo", args=[cita.token]))
        self.assertEqual(cita.canal, Cita.Canal.WEB)
        self.assertIsNone(cita.creada_por)
        self.assertTrue(MensajeEnviado.objects.filter(cita=cita, tipo="agendamiento").exists())

    def test_reserva_paciente_nuevo_menor_con_responsable(self):
        self.client.post(reverse("portal:horas"), {"esp": self.esp.pk, "pol": self.pol.pk, "cupo": self.cupo.pk})
        r = self.client.post(reverse("portal:datos"), {"paso": "rut", "rut": "12.345.678-5"})
        self.assertContains(r, "Es la primera vez de este paciente")
        r = self.client.post(reverse("portal:datos"), {
            "paso": "registro", "rut": "12345678-5", "nombre": "Lucía Paz Fernández", "fecha_nacimiento": "2014-03-15",
            "celular": "+56933332222", "correo": "lucia@correo.cl", "direccion": "Av. Siempre Viva 742", "sexo": "F",
            "nacionalidad": "Chilena", "requiere_responsable": "on",
            "resp-nombre": "Carolina Toro", "resp-rut": "11.111.111-1", "resp-celular": "+56944441111", "resp-parentesco": "Madre",
        })
        self.assertRedirects(r, reverse("portal:confirmar"))
        p = Paciente.objects.get(rut="12345678-5")
        self.assertEqual(p.adulto_responsable.nombre, "Carolina Toro")
        self.client.post(reverse("portal:confirmar"))
        self.assertTrue(Cita.objects.filter(paciente=p).exists())

    def test_hora_tomada_mientras_se_reservaba(self):
        self.client.post(reverse("portal:horas"), {"esp": self.esp.pk, "pol": self.pol.pk, "cupo": self.cupo.pk})
        self.client.post(reverse("portal:datos"), {"paso": "rut", "rut": self.p1.rut})
        self.agendar(self.p2)  # una TENS agenda esa hora antes de que el paciente confirme
        r = self.client.post(reverse("portal:confirmar"), follow=True)
        self.assertContains(r, "Elige otra hora")
        self.assertFalse(Cita.objects.filter(paciente=self.p1).exists())

    def test_sin_horas_anotarse_en_lista_de_espera(self):
        Cupo.objects.update(bloqueado=True)
        r = self.client.get(reverse("portal:horas"), {"esp": self.esp.pk, "pol": self.pol.pk})
        self.assertContains(r, "No hay horas disponibles por ahora")
        self.client.post(reverse("portal:horas"), {"esp": self.esp.pk, "pol": self.pol.pk, "accion": "espera"})
        r = self.client.post(reverse("portal:datos"), {"paso": "rut", "rut": self.p1.rut})
        self.assertRedirects(r, reverse("portal:espera_ok"))
        s = SolicitudEspera.objects.get(paciente=self.p1)
        self.assertEqual((s.canal, s.estado, s.policlinico), ("web", "en_espera", self.pol))

    def test_solo_policlinicos_que_atienden_la_especialidad(self):
        from profesionales.models import Policlinico

        otro = Policlinico.objects.create(nombre="Policlínico Sin Kinesiología")
        r = self.client.get(reverse("portal:inicio"))
        self.assertContains(r, f'data-pols="{self.pol.pk}"')
        r = self.client.get(reverse("portal:horas"), {"esp": self.esp.pk, "pol": otro.pk})
        self.assertRedirects(r, f"{reverse('portal:inicio')}?esp={self.esp.pk}")

    def test_desde_el_portal_se_vuelve_a_la_portada(self):
        self.assertContains(self.client.get(reverse("portal:inicio")), 'href="/"')


class PortalAvisoTests(CitasBase):
    def test_confirmar_desde_el_link(self):
        cita = self.agendar(self.p1)
        self.assertContains(self.client.get(reverse("portal:aviso", args=[cita.token])), f"/c/{cita.token}")
        self.client.post(reverse("portal:accion", args=[cita.token, "confirmar"]))
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.CONFIRMADA)

    def test_cancelar_desde_el_link_libera_la_hora(self):
        cita = self.agendar(self.p1)
        self.client.post(reverse("portal:accion", args=[cita.token, "cancelar"]))
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.CANCELADA)
        self.agendar(self.p2)

    def test_cambiar_hora_desde_el_link(self):
        cita = self.agendar(self.p1)
        r = self.client.get(reverse("portal:cambiar", args=[cita.token]))
        self.assertContains(r, "Cambia tu hora")
        otro = Cupo.objects.filter(fecha=self.manana).exclude(pk=self.cupo.pk).first()
        r = self.client.post(reverse("portal:cambiar", args=[cita.token]), {"cupo": otro.pk})
        nueva = Cita.objects.get(paciente=self.p1, estado=Cita.Estado.AGENDADA)
        self.assertRedirects(r, reverse("portal:resultado", args=[nueva.token]) + "?r=cambiada")
        self.assertEqual(nueva.cupo, otro)
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.CANCELADA)

    def test_codigo_inexistente(self):
        self.assertEqual(self.client.get(reverse("portal:responder", args=["NOEXISTE"])).status_code, 404)


class PortalCorreoTests(CitasBase):
    """Con el envío de correos activado: reserva web, link del correo y confirmación."""

    def setUp(self):
        super().setUp()
        from unittest.mock import patch
        from citas.notificaciones import NotificadorCorreo
        from portal import views
        notificador = NotificadorCorreo()
        for servicio in (views.agendamiento, views.confirmacion):
            p = patch.object(servicio, "notificador", notificador)
            p.start()
            self.addCleanup(p.stop)
        self.p1.correo = "paciente@example.com"
        self.p1.save()

    def test_reserva_web_envia_correo_y_el_link_confirma(self):
        from django.core import mail
        self.client.post(reverse("portal:horas"), {"esp": self.esp.pk, "pol": self.pol.pk, "cupo": self.cupo.pk})
        self.client.post(reverse("portal:datos"), {"paso": "rut", "rut": self.p1.rut})
        self.client.post(reverse("portal:confirmar"))
        cita = Cita.objects.get(paciente=self.p1)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["paciente@example.com"])
        self.assertIn(f"/c/{cita.token}", mail.outbox[0].body)

        self.assertEqual(self.client.get(f"/c/{cita.token}/").status_code, 200)
        self.client.post(reverse("portal:accion", args=[cita.token, "confirmar"]))
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.CONFIRMADA)
        self.assertEqual(cita.respuesta_origen, "paciente")
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[1].subject, "Asistencia confirmada")

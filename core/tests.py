from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from core import roles
from profesionales.models import Policlinico, Profesional


class LoginYRolesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_demo", verbosity=0, stdout=StringIO())

    def test_cargar_demo_crea_administracion_y_una_tens_por_policlinico(self):
        self.assertTrue(roles.tiene_rol(User.objects.get(username="administracion"), roles.ADMINISTRACION))
        self.assertEqual(Policlinico.objects.count(), 7)
        for pol in Policlinico.objects.all():
            self.assertIsNotNone(pol.usuario_tens, pol.nombre)
            self.assertTrue(roles.tiene_rol(pol.usuario_tens, roles.TENS))
            self.assertEqual(roles.policlinico_de(pol.usuario_tens), pol)
        self.assertEqual(Policlinico.objects.get(usuario_tens__username="san_lazaro").nombre, "Policlínico San Lázaro")

    def test_los_profesionales_no_tienen_usuario(self):
        self.assertFalse(User.objects.filter(username="profesional").exists())
        self.assertFalse(Group.objects.filter(name="Profesional").exists())
        self.assertNotIn("usuario", {f.name for f in Profesional._meta.get_fields()})

    def test_cargar_demo_es_idempotente(self):
        call_command("cargar_demo", verbosity=0, stdout=StringIO())
        self.assertEqual(User.objects.filter(username="san_lazaro").count(), 1)
        self.assertEqual(Policlinico.objects.count(), 7)

    def test_portada_publica_y_secciones_protegidas(self):
        resp = self.client.get(reverse("home"))
        self.assertContains(resp, "¿Cómo quieres entrar?")
        self.assertNotContains(resp, "profesional de la Hermandad")
        resp = self.client.get(reverse("citas:agendar"))
        self.assertRedirects(resp, reverse("login") + "?next=/citas/agendar/")

    def test_login_tens_ve_solo_su_policlinico(self):
        self.assertTrue(self.client.login(username="santa_rosa", password="demo1234"))
        r = self.client.get(reverse("home"))
        self.assertContains(r, "Policlínico Santa Rosa")
        for c in r.context["citas"]:
            self.assertEqual(c.cupo.agenda.policlinico.nombre, "Policlínico Santa Rosa")

    def test_inicio_admin_sin_aviso_de_profesional_sin_horas(self):
        self.client.login(username="administracion", password="demo1234")
        r = self.client.get(reverse("home"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "no tiene horas disponibles y hay")

    def test_tens_sin_policlinico_no_entra(self):
        u = User.objects.create_user("sin_pol", password="x")
        u.groups.add(Group.objects.get(name=roles.TENS))
        self.client.force_login(u)
        self.assertEqual(self.client.get(reverse("citas:agendar")).status_code, 403)

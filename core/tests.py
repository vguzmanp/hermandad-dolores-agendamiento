from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from core import roles


class LoginYRolesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_demo", verbosity=0, stdout=StringIO())

    def test_cargar_demo_crea_un_usuario_por_rol(self):
        self.assertTrue(roles.tiene_rol(User.objects.get(username="tens"), roles.TENS))
        self.assertTrue(roles.tiene_rol(User.objects.get(username="administracion"), roles.ADMINISTRACION))
        self.assertTrue(roles.tiene_rol(User.objects.get(username="profesional"), roles.PROFESIONAL))
        self.assertFalse(roles.tiene_rol(User.objects.get(username="profesional"), roles.TENS))

    def test_cargar_demo_es_idempotente(self):
        call_command("cargar_demo", verbosity=0, stdout=StringIO())
        self.assertEqual(User.objects.filter(username="tens").count(), 1)

    def test_portada_publica_y_secciones_protegidas(self):
        resp = self.client.get(reverse("home"))
        self.assertContains(resp, "¿Cómo quieres entrar?")
        resp = self.client.get(reverse("citas:agendar"))
        self.assertRedirects(resp, reverse("login") + "?next=/citas/agendar/")

    def test_login_con_usuario_demo(self):
        ok = self.client.login(username="tens", password="demo1234")
        self.assertTrue(ok)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

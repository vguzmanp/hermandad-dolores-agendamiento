from datetime import date

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from core import roles
from core.exceptions import ReglaNegocioError

from .models import AdultoResponsable, Paciente
from .rut import calcular_dv, es_rut_valido, formatear_rut, normalizar_rut
from .services import PacienteService


def crear_usuario(username, rol):
    u = User.objects.create_user(username, password="x")
    u.groups.add(Group.objects.get_or_create(name=rol)[0])
    return u


class RutTests(TestCase):
    def test_normaliza_y_valida(self):
        self.assertEqual(normalizar_rut("12.345.678-5"), "12345678-5")
        self.assertTrue(es_rut_valido("12.345.678-5"))
        self.assertFalse(es_rut_valido("12.345.678-9"))
        self.assertEqual(calcular_dv(11111111), "1")
        self.assertEqual(formatear_rut("12345678-5"), "12.345.678-5")

    def test_dv_k(self):
        cuerpo = next(n for n in range(10000000, 10001000) if calcular_dv(n) == "K")
        self.assertTrue(es_rut_valido(f"{cuerpo}-k"))


class PacienteServiceTests(TestCase):
    def setUp(self):
        self.tens = crear_usuario("tens", roles.TENS)
        self.admin = crear_usuario("adm", roles.ADMINISTRACION)
        self.servicio = PacienteService()

    def nuevo(self, rut="12345678-5", nacimiento=date(1990, 1, 1)):
        return Paciente(nombre="Paciente Prueba", rut=rut, celular="+56900000000", direccion="Calle 1",
                        fecha_nacimiento=nacimiento, sexo="F")

    def test_registra_y_busca_por_rut(self):
        self.servicio.guardar(self.nuevo(), None, self.tens)
        self.assertIsNotNone(self.servicio.buscar_por_rut("12.345.678-5"))

    def test_rut_duplicado_rechazado_rf02(self):
        self.servicio.guardar(self.nuevo(), None, self.tens)
        with self.assertRaises(ReglaNegocioError):
            self.servicio.guardar(self.nuevo(), None, self.tens)

    def test_menor_sin_responsable_rechazado_rn04(self):
        with self.assertRaises(ReglaNegocioError):
            self.servicio.guardar(self.nuevo(nacimiento=date(2018, 1, 1)), None, self.tens)

    def test_menor_con_responsable(self):
        resp = AdultoResponsable(nombre="Madre", rut="11111111-1", parentesco="Madre", celular="+569")
        p = self.servicio.guardar(self.nuevo(nacimiento=date(2018, 1, 1)), resp, self.tens)
        self.assertEqual(p.adulto_responsable.nombre, "Madre")

    def test_advertencia_cesfam_rn05(self):
        p = self.servicio.guardar(self.nuevo(), None, self.tens)
        self.assertTrue(any("CESFAM" in a for a in p.advertencias))

    def test_solo_tens_registra(self):
        with self.assertRaises(PermissionDenied):
            self.servicio.guardar(self.nuevo(), None, self.admin)


class PacienteVistasTests(TestCase):
    def setUp(self):
        self.tens = crear_usuario("tens", roles.TENS)
        self.client.force_login(self.tens)

    def test_buscar_rut_inexistente_lleva_al_registro(self):
        resp = self.client.get(reverse("pacientes:buscar_rut"), {"rut": "12.345.678-5"})
        self.assertRedirects(resp, reverse("pacientes:lista") + "?rut=12345678-5")

    def test_registrar_por_formulario(self):
        resp = self.client.post(reverse("pacientes:lista"), {
            "rut": "12.345.678-5", "nombre": "Ana Prueba", "fecha_nacimiento": "1990-05-05", "sexo": "F",
            "nacionalidad": "Chilena", "celular": "+56911111111", "correo": "", "direccion": "Calle 1",
        })
        p = Paciente.objects.get(rut="12345678-5")
        self.assertRedirects(resp, reverse("pacientes:editar", args=[p.pk]))
        # Ahora la búsqueda por RUT lleva a su ficha (RF-02)
        resp = self.client.get(reverse("pacientes:buscar_rut"), {"rut": "12345678-5"})
        self.assertRedirects(resp, reverse("pacientes:editar", args=[p.pk]))

    def test_menor_exige_responsable_en_formulario(self):
        self.client.post(reverse("pacientes:lista"), {
            "rut": "12.345.678-5", "nombre": "Niño Prueba", "fecha_nacimiento": "2018-05-05", "sexo": "M",
            "nacionalidad": "Chilena", "celular": "+56911111111", "direccion": "Calle 1", "requiere_responsable": "on",
        })
        self.assertFalse(Paciente.objects.exists())

    def test_usuario_sin_rol_no_accede_a_pacientes(self):
        self.client.force_login(User.objects.create_user("sin_rol", password="x"))
        self.assertEqual(self.client.get(reverse("pacientes:lista")).status_code, 403)


class DocumentosTests(TestCase):
    def setUp(self):
        self.tens = crear_usuario("tens", roles.TENS)
        self.p = Paciente.objects.create(nombre="Paciente Doc", rut="12345678-5", celular="+56900000000",
                                         direccion="Calle 1", fecha_nacimiento=date(1990, 1, 1), sexo="F")
        self.client.force_login(self.tens)

    def subir(self, nombre="cesfam.pdf", tipo="cesfam", contenido=b"%PDF-1.4 prueba"):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return self.client.post(reverse("documentos:lista") + f"?paciente={self.p.pk}",
                                {"paciente": self.p.pk, "tipo": tipo, "archivo": SimpleUploadedFile(nombre, contenido)})

    def test_subir_cesfam_resuelve_rn05_y_queda_en_historial(self):
        import shutil, tempfile
        from django.test import override_settings
        carpeta = tempfile.mkdtemp()
        try:
            with override_settings(MEDIA_ROOT=carpeta):
                self.assertTrue(any("CESFAM" in a for a in self.p.advertencias))
                self.subir()
                self.p.refresh_from_db()
                self.assertTrue(self.p.inscrito_cesfam)
                doc = self.p.documentos.get()
                r = self.client.get(reverse("documentos:archivo", args=[doc.pk]))
                self.assertEqual(r.status_code, 200)
                r.close()
                self.client.post(reverse("documentos:eliminar", args=[doc.pk]))
                acciones = list(self.p.operaciones_documentos.values_list("accion", flat=True))
                self.assertCountEqual(acciones, ["adjunto", "consulto", "elimino"])
        finally:
            shutil.rmtree(carpeta, ignore_errors=True)

    def test_formato_no_permitido(self):
        self.subir(nombre="virus.exe")
        self.assertFalse(self.p.documentos.exists())

"""
Carga datos ficticios para la demostración.

    python manage.py cargar_demo           # crea/actualiza (idempotente)
    python manage.py cargar_demo --reset   # borra los datos de dominio y los vuelve a crear

Todos los datos (nombres, RUT, teléfonos, policlínicos) son FICTICIOS.
"""
from datetime import date, time, timedelta

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from agenda.models import Agenda, Cupo
from agenda.services import AgendaService
from core import roles
from pacientes.models import AdultoResponsable, Paciente
from pacientes.rut import calcular_dv
from profesionales.models import Especialidad, Policlinico, Profesional

CLAVE_DEMO = "demo1234"


def rut(cuerpo: int) -> str:
    return f"{cuerpo}-{calcular_dv(cuerpo)}"


# nombre, rut, nacimiento, sexo, nacionalidad, celular, correo, dirección, cesfam (None = sin inscripción)
PACIENTES_DEMO = [
    ("María José Pérez Lagos", 15234871, date(1985, 3, 14), "F", "Chilena", "+56911112222", "mjperez@demo.cl", "Av. Los Aromos 123, Santiago", "CESFAM Villa Esperanza"),
    ("Juan Carlos Fuentes Díaz", 9876543, date(1958, 7, 2), "M", "Chilena", "+56922223333", "", "Pasaje Las Rosas 45, Santiago", "CESFAM Villa Esperanza"),
    ("Ana Luisa Contreras Vera", 18765432, date(1993, 11, 21), "F", "Chilena", "+56933334444", "ana.contreras@demo.cl", "Calle Nueva 890, Independencia", None),
    ("Pedro Antonio Morales Silva", 12345670, date(1971, 1, 30), "M", "Chilena", "+56944445555", "", "Av. Central 1500, Recoleta", "CESFAM Los Almendros"),
    ("Valentina Ignacia Torres Rojas", 24123456, date(2015, 5, 9), "F", "Chilena", "+56955556666", "", "Los Jazmines 77, Santiago", "CESFAM Los Almendros"),
    ("Tomás Benjamín Araya Núñez", 25234567, date(2018, 9, 17), "M", "Chilena", "+56966667777", "", "Los Jazmines 79, Santiago", None),
    ("Rosa Elena Gutiérrez Pino", 6543219, date(1949, 12, 3), "F", "Chilena", "+56977778888", "", "San Pablo 3456, Quinta Normal", "CESFAM Villa Esperanza"),
    ("Luis Alberto Castillo Mena", 16789012, date(1988, 4, 25), "M", "Peruana", "+56988889999", "lcastillo@demo.cl", "Mapocho 2210, Santiago", "CESFAM Los Almendros"),
    ("Camila Fernanda Reyes Ortiz", 19876543, date(1999, 8, 11), "F", "Chilena", "+56999990000", "camila.reyes@demo.cl", "Brasil 156, Santiago", "CESFAM Villa Esperanza"),
    ("Jean Pierre Louis", 26345678, date(1990, 2, 19), "M", "Haitiana", "+56910101010", "", "Esperanza 34, Estación Central", None),
    ("Sofía Antonia Bravo Leiva", 23456789, date(2010, 6, 1), "F", "Chilena", "+56912121212", "", "Huérfanos 3000, Santiago", "CESFAM Los Almendros"),
    ("Héctor Manuel Salinas Cortés", 8765432, date(1962, 10, 8), "M", "Chilena", "+56913131313", "hsalinas@demo.cl", "Catedral 2500, Santiago", "CESFAM Villa Esperanza"),
]

# rut del paciente -> (nombre, rut, parentesco, celular)
RESPONSABLES_DEMO = {
    24123456: ("Claudia Rojas Méndez", 14567890, "Madre", "+56955550001"),
    25234567: ("Ricardo Araya Soto", 13456789, "Padre", "+56966660002"),
    23456789: ("Paula Leiva Contreras", 15678901, "Madre", "+56912120003"),
    6543219: ("Marcela Gutiérrez Pino", 11223344, "Hija (dependencia severa)", "+56977770004"),
}

# 6 policlínicos + Telemedicina (nombres ficticios)
POLICLINICOS_DEMO = [
    ("Policlínico San Lázaro", "Av. Matucana 1020, Santiago", False),
    ("Policlínico Santa Rosa", "Santa Rosa 455, Santiago", False),
    ("Policlínico Los Olivos", "Los Olivos 210, Recoleta", False),
    ("Policlínico Nuestra Señora del Carmen", "Independencia 1345, Independencia", False),
    ("Policlínico El Buen Samaritano", "San Pablo 2789, Quinta Normal", False),
    ("Policlínico Santa Clara", "Av. Ecuador 3890, Estación Central", False),
    ("Telemedicina", "Atención remota por videollamada", True),
]

# nombre, duración cupo (min), sesiones por tratamiento, permite agendar todas las sesiones
ESPECIALIDADES_DEMO = [
    ("Medicina General", 30, 1, False),
    ("Kinesiología", 45, 10, True),
    ("Psicología", 45, 8, True),
    ("Fonoaudiología", 45, 6, True),
    ("Nutrición", 30, 1, False),
    ("Podología", 30, 1, False),
]

# nombre, rut, especialidad, usuario demo
PROFESIONALES_DEMO = [
    ("Andrés Soto Valenzuela", 13579246, "Medicina General", "profesional"),
    ("Daniela Herrera Campos", 14682579, "Medicina General", None),
    ("Felipe Navarro Ibáñez", 15793680, "Kinesiología", None),
    ("Constanza Vidal Riquelme", 16804791, "Psicología", None),
    ("Ignacio Paredes Molina", 17915802, "Fonoaudiología", None),
    ("Fernanda Lagos Espinoza", 12468013, "Nutrición", None),
    ("Rodrigo Cáceres Toro", 11357924, "Podología", None),
]

# profesional (índice), policlínico (índice), día (0=lunes), hora inicio, hora fin
AGENDAS_DEMO = [
    (0, 0, 0, "09:00", "12:00"), (0, 0, 2, "09:00", "12:00"), (0, 6, 4, "15:00", "17:00"),
    (1, 1, 1, "08:30", "12:30"), (1, 3, 3, "14:00", "17:00"),
    (2, 2, 0, "14:00", "17:00"), (2, 2, 2, "14:00", "17:00"), (2, 4, 4, "09:00", "12:00"),
    (3, 5, 1, "15:00", "18:00"), (3, 6, 3, "09:00", "12:00"),
    (4, 3, 0, "09:00", "12:00"), (4, 1, 3, "09:00", "12:00"),
    (5, 4, 1, "09:00", "12:00"), (5, 6, 4, "10:00", "12:00"),
    (6, 0, 3, "14:00", "16:00"), (6, 5, 4, "09:00", "11:00"),
]

USUARIOS_DEMO = [
    # username, nombre, apellido, rol, es_superusuario
    ("admin", "Admin", "Sistema", None, True),
    ("administracion", "Carolina", "Muñoz", roles.ADMINISTRACION, False),
    ("tens", "Javiera", "Rojas", roles.TENS, False),
    ("profesional", "Andrés", "Soto", roles.PROFESIONAL, False),
]


class Command(BaseCommand):
    help = "Carga roles, usuarios de prueba y datos ficticios para la demo."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Borra los datos de dominio antes de cargar.")

    @transaction.atomic
    def handle(self, *args, **opciones):
        if opciones["reset"]:
            self.borrar_datos()
        usuarios = self.crear_roles_y_usuarios()
        self.cargar_dominio(usuarios)
        self.stdout.write(self.style.SUCCESS("Datos de demostración cargados."))
        self.stdout.write("Usuarios (contraseña '%s'): %s" % (CLAVE_DEMO, ", ".join(u[0] for u in USUARIOS_DEMO)))

    # ------------------------------------------------------------------ roles
    def crear_roles_y_usuarios(self) -> dict[str, User]:
        for nombre in roles.TODOS_LOS_ROLES:
            Group.objects.get_or_create(name=nombre)
        usuarios = {}
        for username, nombre, apellido, rol, es_super in USUARIOS_DEMO:
            u, creado = User.objects.get_or_create(
                username=username,
                defaults={"first_name": nombre, "last_name": apellido, "email": f"{username}@demo.local"},
            )
            u.is_superuser = es_super
            u.is_staff = es_super
            if creado:
                u.set_password(CLAVE_DEMO)
            u.save()
            if rol:
                u.groups.set([Group.objects.get(name=rol)])
            usuarios[username] = u
        self.stdout.write(f"  Roles: {', '.join(roles.TODOS_LOS_ROLES)}")
        return usuarios

    # --------------------------------------------------------------- dominio
    def borrar_datos(self):
        Cupo.objects.all().delete()
        Agenda.objects.all().delete()
        Profesional.objects.all().delete()
        Especialidad.objects.all().delete()
        Policlinico.objects.all().delete()
        Paciente.objects.all().delete()
        self.stdout.write("  Datos de dominio eliminados.")

    def cargar_dominio(self, usuarios):
        self.cargar_pacientes(usuarios["tens"])
        self.cargar_agendas(usuarios)

    def cargar_pacientes(self, tens):
        for nombre, cuerpo, nac, sexo, nacionalidad, celular, correo, direccion, cesfam in PACIENTES_DEMO:
            p, _ = Paciente.objects.update_or_create(
                rut=rut(cuerpo),
                defaults=dict(
                    nombre=nombre, fecha_nacimiento=nac, sexo=sexo, nacionalidad=nacionalidad,
                    celular=celular, correo=correo, direccion=direccion,
                    inscrito_cesfam=cesfam is not None, cesfam=cesfam or "",
                    requiere_responsable=cuerpo in RESPONSABLES_DEMO, registrado_por=tens,
                ),
            )
            if cuerpo in RESPONSABLES_DEMO:
                r_nombre, r_rut, parentesco, r_cel = RESPONSABLES_DEMO[cuerpo]
                AdultoResponsable.objects.update_or_create(
                    paciente=p, defaults=dict(nombre=r_nombre, rut=rut(r_rut), parentesco=parentesco, celular=r_cel)
                )
        self.stdout.write(f"  Pacientes: {Paciente.objects.count()}")

    def cargar_agendas(self, usuarios):
        polis = []
        for nombre, direccion, tele in POLICLINICOS_DEMO:
            pol, _ = Policlinico.objects.update_or_create(
                nombre=nombre, defaults={"direccion": direccion, "es_telemedicina": tele}
            )
            polis.append(pol)
        esps = {}
        for nombre, dur, ses, todas in ESPECIALIDADES_DEMO:
            esps[nombre], _ = Especialidad.objects.update_or_create(
                nombre=nombre,
                defaults={"duracion_cupo_min": dur, "sesiones_por_tratamiento": ses, "permite_agendar_todas_sesiones": todas},
            )
        profs = []
        for nombre, cuerpo, esp, username in PROFESIONALES_DEMO:
            prof, _ = Profesional.objects.update_or_create(
                rut=rut(cuerpo),
                defaults={"nombre": nombre, "especialidad": esps[esp], "usuario": usuarios.get(username),
                          "correo": f"{nombre.split()[0].lower()}@demo.cl"},
            )
            profs.append(prof)

        servicio = AgendaService()
        admin = usuarios["administracion"]
        hoy = timezone.localdate()
        inicio_semana = hoy - timedelta(days=hoy.weekday())
        n_cupos = 0
        for i_prof, i_pol, dia, hi, hf in AGENDAS_DEMO:
            agenda, _ = Agenda.objects.get_or_create(
                profesional=profs[i_prof], policlinico=polis[i_pol], dia_semana=dia,
                hora_inicio=time.fromisoformat(hi),
                defaults={"hora_fin": time.fromisoformat(hf), "vigente_desde": inicio_semana},
            )
            n_cupos += servicio.generar_cupos(agenda, hoy, None, admin)
        self.stdout.write(
            f"  Policlínicos: {len(polis)} · Especialidades: {len(esps)} · Profesionales: {len(profs)} · "
            f"Agendas: {Agenda.objects.count()} · Cupos nuevos: {n_cupos}"
        )

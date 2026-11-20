"""
Carga datos ficticios para la demostración.

    python manage.py cargar_demo           # crea/actualiza (idempotente)
    python manage.py cargar_demo --reset   # borra los datos de dominio y los vuelve a crear

Todos los datos (nombres, RUT, teléfonos, policlínicos) son FICTICIOS.
"""
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction

from core import roles

CLAVE_DEMO = "demo1234"

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
        """Se extiende a medida que se agregan módulos."""

    def cargar_dominio(self, usuarios):
        """Se extiende a medida que se agregan módulos."""

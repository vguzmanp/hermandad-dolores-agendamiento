"""
Carga datos ficticios para la demostración.

    python manage.py cargar_demo           # crea lo que falte (idempotente)
    python manage.py cargar_demo --reset   # borra los datos de dominio y los vuelve a crear

Todos los datos (nombres, RUT, teléfonos, policlínicos) son FICTICIOS. Las fechas
se calculan desde el día en que se ejecuta: conviene correrlo con --reset el día
de la demostración.
"""
import random
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone

from agenda.models import Agenda, Cupo
from agenda.services import AgendaService
from asistencia.models import Asistencia
from citas.models import Cita, MensajeEnviado
from citas.repositories import CitaRepositoryPostgres
from citas.services import AgendamientoService, ConfirmacionService
from core import roles
from lista_espera.models import SolicitudEspera
from pacientes.models import AdultoResponsable, DocumentoPaciente, OperacionDocumento, Paciente
from pacientes.rut import calcular_dv
from profesionales.models import Especialidad, Policlinico, Profesional

CLAVE_DEMO = "demo1234"
SEMANAS_HISTORIA = 10


def rut(cuerpo: int) -> str:
    return f"{cuerpo}-{calcular_dv(cuerpo)}"


USUARIOS_DEMO = [
    # username, nombre, apellido, rol, es_superusuario
    ("admin", "Admin", "Sistema", None, True),
    ("administracion", "Carolina", "Muñoz", roles.ADMINISTRACION, False),
]
# Usuarios de versiones anteriores de la demo que ya no corresponden (los profesionales no usan el sistema).
USUARIOS_OBSOLETOS = ("tens", "profesional")

# nombre, dirección, telemedicina, usuario TENS/TONS (se llama como el policlínico)
POLICLINICOS_DEMO = [
    ("Policlínico San Lázaro", "Av. Matucana 1020, Santiago", False, "san_lazaro"),
    ("Policlínico Santa Rosa", "Santa Rosa 455, Santiago", False, "santa_rosa"),
    ("Policlínico Los Olivos", "Los Olivos 210, Recoleta", False, "los_olivos"),
    ("Policlínico El Carmen", "Independencia 1345, Independencia", False, "el_carmen"),
    ("Policlínico Buen Samaritano", "San Pablo 2789, Quinta Normal", False, "buen_samaritano"),
    ("Policlínico Santa Clara", "Av. Ecuador 3890, Estación Central", False, "santa_clara"),
    ("Telemedicina", "Atención remota por videollamada", True, "telemedicina"),
]
NOMBRES_ANTERIORES = {"Policlínico Nuestra Señora del Carmen": "Policlínico El Carmen",
                      "Policlínico El Buen Samaritano": "Policlínico Buen Samaritano"}

# nombre, duración (min), sesiones por tratamiento, permite agendar todas las sesiones
ESPECIALIDADES_DEMO = [
    ("Medicina General", 30, 1, False),
    ("Kinesiología", 30, 10, True),
    ("Psicología", 45, 8, True),
    ("Fonoaudiología", 45, 6, True),
    ("Nutrición", 30, 1, False),
    ("Enfermería", 30, 1, False),
]

# nombre y título, rut, especialidad
PROFESIONALES_DEMO = [
    ("Dr. Andrés Soto Valenzuela", 13579246, "Medicina General"),
    ("Dra. Daniela Herrera Campos", 14682579, "Medicina General"),
    ("Klgo. Felipe Navarro Ibáñez", 15793680, "Kinesiología"),
    ("Klga. Camila Fuentes Mora", 16127394, "Kinesiología"),
    ("Ps. Constanza Vidal Riquelme", 16804791, "Psicología"),
    ("Flgo. Ignacio Paredes Molina", 17915802, "Fonoaudiología"),
    ("Nut. Fernanda Lagos Espinoza", 12468013, "Nutrición"),
    ("Enf. Marta Ibáñez Toro", 11357924, "Enfermería"),
]

# profesional (índice), policlínico (índice), día (0=lunes), desde, hasta
AGENDAS_DEMO = [
    (0, 0, 0, "09:00", "12:00"), (0, 0, 2, "09:00", "12:00"), (0, 6, 4, "15:00", "17:00"),
    (1, 1, 1, "08:30", "12:30"), (1, 3, 3, "14:00", "17:00"),
    (2, 2, 0, "14:00", "17:00"), (2, 2, 2, "14:00", "17:00"), (2, 4, 4, "09:00", "12:00"),
    (3, 0, 1, "09:00", "13:00"), (3, 0, 3, "09:00", "13:00"), (3, 5, 4, "09:00", "13:00"),
    (4, 5, 1, "15:00", "18:00"), (4, 6, 3, "09:00", "12:00"),
    (5, 3, 0, "09:00", "12:00"), (5, 1, 3, "09:00", "12:00"),
    (6, 4, 1, "09:00", "12:00"), (6, 6, 4, "10:00", "12:00"),
    (7, 1, 0, "09:00", "12:00"), (7, 1, 2, "09:00", "12:00"), (7, 2, 4, "09:00", "12:00"),
]

# Pacientes con nombre fijo (se usan en los escenarios de la demo)
# nombre, rut, nacimiento, sexo, nacionalidad, celular, correo, dirección, inscrito CESFAM
PACIENTES_DEMO = [
    ("María José Pérez Lagos", 15234871, date(1985, 3, 14), "F", "Chilena", "+56911112222", "mjperez@example.com", "Av. Los Aromos 123, Santiago", True),
    ("Juan Carlos Fuentes Díaz", 9876543, date(1958, 7, 2), "M", "Chilena", "+56922223333", "", "Pasaje Las Rosas 45, Santiago", True),
    ("Ana Luisa Contreras Vera", 18765432, date(1993, 11, 21), "F", "Chilena", "+56933334444", "ana.contreras@example.com", "Calle Nueva 890, Independencia", False),
    ("Pedro Antonio Morales Silva", 12345670, date(1971, 1, 30), "M", "Chilena", "+56944445555", "", "Av. Central 1500, Recoleta", True),
    ("Valentina Ignacia Torres Rojas", 24123456, date(2015, 5, 9), "F", "Chilena", "+56955556666", "", "Los Jazmines 77, Santiago", True),
    ("Tomás Benjamín Araya Núñez", 25234567, date(2018, 9, 17), "M", "Chilena", "+56966667777", "", "Los Jazmines 79, Santiago", False),
    ("Rosa Elena Gutiérrez Pino", 6543219, date(1949, 12, 3), "F", "Chilena", "+56977778888", "", "San Pablo 3456, Quinta Normal", True),
    ("Luis Alberto Castillo Mena", 16789012, date(1988, 4, 25), "M", "Peruana", "+56988889999", "lcastillo@example.com", "Mapocho 2210, Santiago", True),
    ("Camila Fernanda Reyes Ortiz", 19876543, date(1999, 8, 11), "F", "Chilena", "+56999990000", "camila.reyes@example.com", "Brasil 156, Santiago", True),
    ("Jean Pierre Louis", 26345678, date(1990, 2, 19), "M", "Haitiana", "+56910101010", "", "Esperanza 34, Estación Central", False),
    ("Sofía Antonia Bravo Leiva", 23456789, date(2010, 6, 1), "F", "Chilena", "+56912121212", "", "Huérfanos 3000, Santiago", True),
    # celular fijo (no es móvil): su aviso por WhatsApp falla, para mostrar «Reintentar aviso»
    ("Héctor Manuel Salinas Cortés", 8765432, date(1962, 10, 8), "M", "Chilena", "+56 2 2345 6789", "", "Catedral 2500, Santiago", True),
    ("Joaquín Andrés Molina Soto", 22456789, date(2016, 6, 9), "M", "Chilena", "+56987654321", "", "Las Acacias 450, Recoleta", False),
]

RESPONSABLES_DEMO = {
    24123456: ("Claudia Rojas Méndez", 14567890, "Madre", "+56955550001"),
    25234567: ("Ricardo Araya Soto", 13456789, "Padre", "+56966660002"),
    23456789: ("Paula Leiva Contreras", 15678901, "Madre", "+56912120003"),
    6543219: ("Marcela Gutiérrez Pino", 11223344, "Hijo/a", "+56977770004"),
    22456789: ("Andrea Soto Pérez", 14321987, "Madre", "+56987650005"),
}

NOMBRES_F = ["Carmen", "Javiera", "Isidora", "Antonella", "Florencia", "Daniela", "Patricia", "Gloria", "Francisca",
             "Catalina", "Yesenia", "Marisol", "Teresa", "Luisa", "Agustina", "Martina", "Fernanda", "Paola"]
NOMBRES_M = ["José", "Matías", "Benjamín", "Vicente", "Cristóbal", "Jorge", "Manuel", "Sergio", "Francisco",
             "Diego", "Ricardo", "Alonso", "Gabriel", "Mauricio", "Raúl", "Tomás", "Emilio", "Óscar"]
APELLIDOS = ["González", "Muñoz", "Rojas", "Díaz", "Pérez", "Soto", "Contreras", "Silva", "Martínez", "Sepúlveda",
             "Morales", "Rodríguez", "López", "Fuentes", "Hernández", "Torres", "Araya", "Flores", "Espinoza",
             "Valenzuela", "Castillo", "Tapia", "Reyes", "Gutiérrez", "Castro", "Pizarro", "Álvarez", "Vásquez"]
NACIONALIDADES = ["Chilena"] * 14 + ["Venezolana"] * 3 + ["Peruana"] * 2 + ["Haitiana"] * 2 + ["Colombiana", "Boliviana"]
CALLES = ["Av. Independencia", "San Pablo", "Mapocho", "Recoleta", "Matucana", "Catedral", "Agustinas", "Bulnes"]


def proximo_habil(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


class Command(BaseCommand):
    help = "Carga roles, usuarios de prueba y datos ficticios para la demo."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Borra los datos de dominio antes de cargar.")

    @transaction.atomic
    def handle(self, *args, **opciones):
        self.rnd = random.Random(2026)
        if opciones["reset"]:
            self.borrar_datos()
        usuarios = self.crear_roles_y_usuarios()
        self.cargar_dominio(usuarios)
        self.stdout.write(self.style.SUCCESS("Datos de demostración cargados."))
        nombres = [u[0] for u in USUARIOS_DEMO] + [p[3] for p in POLICLINICOS_DEMO]
        self.stdout.write("Usuarios (contraseña '%s'): %s" % (CLAVE_DEMO, ", ".join(nombres)))

    # ------------------------------------------------------------------ roles
    def crear_roles_y_usuarios(self) -> dict[str, User]:
        for nombre in roles.TODOS_LOS_ROLES:
            Group.objects.get_or_create(name=nombre)
        Group.objects.filter(name="Profesional").delete()
        for viejo in User.objects.filter(username__in=USUARIOS_OBSOLETOS, is_superuser=False):
            try:
                viejo.delete()
            except ProtectedError:  # tiene citas registradas a su nombre: se desactiva
                viejo.groups.clear()
                viejo.is_active = False
                viejo.save()
        usuarios = {}
        tens = [(u, "TENS/TONS", nombre.replace("Policlínico ", ""), roles.TENS, False)
                for nombre, _, _, u in POLICLINICOS_DEMO]
        for username, nombre, apellido, rol, es_super in USUARIOS_DEMO + tens:
            u, creado = User.objects.get_or_create(
                username=username, defaults={"first_name": nombre, "last_name": apellido, "email": f"{username}@demo.local"})
            u.is_superuser = u.is_staff = es_super
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
        OperacionDocumento.objects.all().delete()
        for d in DocumentoPaciente.objects.exclude(archivo=""):
            d.archivo.delete(save=False)
        DocumentoPaciente.objects.all().delete()
        SolicitudEspera.objects.all().delete()
        Asistencia.objects.all().delete()
        MensajeEnviado.objects.all().delete()
        Cita.objects.all().delete()
        Cupo.objects.all().delete()
        Agenda.objects.all().delete()
        Profesional.objects.all().delete()
        Especialidad.objects.all().delete()
        Policlinico.objects.all().delete()
        Paciente.objects.all().delete()
        self.stdout.write("  Datos de dominio eliminados.")

    def cargar_dominio(self, usuarios):
        self.hoy = timezone.localdate()
        tens_central = usuarios["san_lazaro"]
        self.cargar_pacientes(tens_central)
        self.cargar_agendas(usuarios)
        if Cita.objects.exists():
            self.stdout.write("  Citas: ya existen, no se modifican (use --reset para recrearlas).")
            return
        self.cargar_historial()
        self.cargar_citas_proximas()
        self.cargar_proximos_dias()
        self.cargar_lista_espera()
        self.cargar_documentos(tens_central)

    def tens_de(self, cupo) -> User:
        """Usuario TENS/TONS del policlínico del cupo (cada TENS agenda solo en su policlínico)."""
        return self.tens_por_pol[cupo.agenda.policlinico_id]

    def cargar_pacientes(self, tens):
        for nombre, cuerpo, nac, sexo, nacionalidad, celular, correo, direccion, cesfam in PACIENTES_DEMO:
            p, _ = Paciente.objects.update_or_create(rut=rut(cuerpo), defaults=dict(
                nombre=nombre, fecha_nacimiento=nac, sexo=sexo, nacionalidad=nacionalidad, celular=celular,
                correo=correo, direccion=direccion, inscrito_cesfam=cesfam, cesfam="CESFAM Villa Esperanza" if cesfam else "",
                requiere_responsable=cuerpo in RESPONSABLES_DEMO, registrado_por=tens))
            if cuerpo in RESPONSABLES_DEMO:
                r_nombre, r_rut, parentesco, r_cel = RESPONSABLES_DEMO[cuerpo]
                AdultoResponsable.objects.update_or_create(
                    paciente=p, defaults=dict(nombre=r_nombre, rut=rut(r_rut), parentesco=parentesco, celular=r_cel))
        # Pacientes adicionales generados (para que los reportes tengan volumen)
        for i in range(48):
            cuerpo = 7_100_000 + i * 371_137
            if Paciente.objects.filter(rut=rut(cuerpo)).exists():
                continue
            sexo = "F" if i % 9 not in (1, 4, 7, 8) else "M"
            nombre = f"{self.rnd.choice(NOMBRES_F if sexo == 'F' else NOMBRES_M)} {self.rnd.choice(APELLIDOS)} {self.rnd.choice(APELLIDOS)}"
            edad = self.rnd.choice([5, 9, 12, 19, 24, 33, 41, 47, 55, 61, 66, 70, 74, 78, 82])
            nac = date(self.hoy.year - edad, self.rnd.randint(1, 12), self.rnd.randint(1, 28))
            p = Paciente.objects.create(
                rut=rut(cuerpo), nombre=nombre, fecha_nacimiento=nac, sexo=sexo, nacionalidad=self.rnd.choice(NACIONALIDADES),
                celular=f"+569{self.rnd.randint(10000000, 99999999)}",
                direccion=f"{self.rnd.choice(CALLES)} {self.rnd.randint(100, 3999)}, Santiago",
                inscrito_cesfam=self.rnd.random() < .8, requiere_responsable=edad < 18, registrado_por=tens)
            if edad < 18:
                AdultoResponsable.objects.create(
                    paciente=p, nombre=f"{self.rnd.choice(NOMBRES_F)} {p.nombre.split()[1]}", rut=rut(cuerpo + 11),
                    parentesco="Madre", celular=f"+569{self.rnd.randint(10000000, 99999999)}")
        self.stdout.write(f"  Pacientes: {Paciente.objects.count()}")

    def cargar_agendas(self, usuarios):
        for anterior, nuevo in NOMBRES_ANTERIORES.items():
            if not Policlinico.objects.filter(nombre=nuevo).exists():
                Policlinico.objects.filter(nombre=anterior).update(nombre=nuevo)
        polis = []
        for n, d, t, username in POLICLINICOS_DEMO:
            Policlinico.objects.filter(usuario_tens=usuarios[username]).exclude(nombre=n).update(usuario_tens=None)
            polis.append(Policlinico.objects.update_or_create(nombre=n, defaults={
                "direccion": d, "es_telemedicina": t, "usuario_tens": usuarios[username]})[0])
        self.tens_por_pol = {p.pk: p.usuario_tens for p in polis}
        esps = {n: Especialidad.objects.update_or_create(nombre=n, defaults={
            "duracion_cupo_min": dur, "sesiones_por_tratamiento": ses, "permite_agendar_todas_sesiones": todas})[0]
            for n, dur, ses, todas in ESPECIALIDADES_DEMO}
        profs = [Profesional.objects.update_or_create(rut=rut(cuerpo), defaults={
            "nombre": nombre, "especialidad": esps[esp]})[0]
            for nombre, cuerpo, esp in PROFESIONALES_DEMO]
        servicio = AgendaService()
        inicio_hist = self.hoy - timedelta(weeks=SEMANAS_HISTORIA, days=self.hoy.weekday())
        n_cupos = 0
        for i_prof, i_pol, dia, hi, hf in AGENDAS_DEMO:
            agenda, _ = Agenda.objects.get_or_create(
                profesional=profs[i_prof], policlinico=polis[i_pol], dia_semana=dia, hora_inicio=time.fromisoformat(hi),
                defaults={"hora_fin": time.fromisoformat(hf), "vigente_desde": inicio_hist})
            # historial (cupos pasados) + próximas semanas
            horarios = list(servicio.horarios_del_bloque(agenda))
            d = inicio_hist + timedelta(days=dia)
            while d < self.hoy:
                for ini, fin in horarios:
                    _, creado = Cupo.objects.get_or_create(agenda=agenda, fecha=d, hora_inicio=ini, defaults={"hora_fin": fin})
                    n_cupos += creado
                d += timedelta(weeks=1)
            n_cupos += servicio.generar_cupos(agenda, self.hoy, None, usuarios["administracion"])
        # Enfermería: la profesional está con licencia → todas sus horas futuras bloqueadas
        Cupo.objects.filter(agenda__profesional=profs[7], fecha__gte=self.hoy).update(
            bloqueado=True, motivo_bloqueo="Licencia médica")
        self.profs, self.polis, self.esps = profs, polis, esps
        self.stdout.write(f"  Policlínicos: {len(polis)} · Especialidades: {len(esps)} · Profesionales: {len(profs)} · "
                          f"Bloques semanales: {Agenda.objects.count()} · Cupos nuevos: {n_cupos}")

    # ------------------------------------------------------------- historial
    def cargar_historial(self):
        """Citas pasadas con asistencia registrada (para reportes)."""
        pacientes = list(Paciente.objects.all())
        ocupado = set()
        citas = []
        for cupo in Cupo.objects.filter(fecha__lt=self.hoy).select_related("agenda"):
            tens = self.tens_de(cupo)
            if self.rnd.random() > .62:
                continue
            for _ in range(5):
                p = self.rnd.choice(pacientes)
                if (p.pk, cupo.fecha, cupo.hora_inicio) not in ocupado:
                    break
            ocupado.add((p.pk, cupo.fecha, cupo.hora_inicio))
            r = self.rnd.random()
            estado = "cancelada" if r < .1 else ("sin_respuesta" if r < .18 else "confirmada")
            creada = timezone.make_aware(datetime.combine(cupo.fecha - timedelta(days=self.rnd.randint(3, 20)), time(10)))
            citas.append(Cita(cupo=cupo, paciente=p, estado=estado, creada_por=tens, creada_en=creada,
                              canal=self.rnd.choice(["presencial", "telefono", "telefono", "whatsapp", "web"]),
                              recordatorio_enviado_en=creada + timedelta(days=1),
                              respuesta_origen="" if estado == "sin_respuesta" else self.rnd.choice(["paciente", "tens"])))
        Cita.objects.bulk_create(citas)
        asistencias = []
        for c in Cita.objects.filter(cupo__fecha__lt=self.hoy).exclude(estado="cancelada").select_related("cupo__agenda"):
            prob = .93 if c.estado == "confirmada" else .55
            asistencias.append(Asistencia(cita=c, asistio=self.rnd.random() < prob, registrada_por=self.tens_de(c.cupo),
                                          registrada_en=timezone.make_aware(datetime.combine(c.cupo.fecha, time(18)))))
        Asistencia.objects.bulk_create(asistencias)
        self.stdout.write(f"  Historial: {len(citas)} citas pasadas · {len(asistencias)} asistencias registradas")

    # ------------------------------------------------------- próximas citas
    def cargar_citas_proximas(self):
        repo = CitaRepositoryPostgres()
        ag = AgendamientoService(repo)
        conf = ConfirmacionService(repo, agendamiento=ag)
        P = {p.rut: p for p in Paciente.objects.all()}
        pac = lambda cuerpo: P[rut(cuerpo)]  # noqa: E731
        manana = proximo_habil(self.hoy)
        prof_kine = self.profs[3]  # Klga. Camila Fuentes (atiende mar, jue y vie)

        def libres(prof, fecha, n=None):
            lst = list(repo.cupos_libres({"desde": fecha, "hasta": fecha, "profesional": prof}))
            return lst[:n] if n else lst

        # --- Hoy: citas para registrar asistencia (directo en la BD, aunque la hora ya haya pasado)
        fijos = {rut(x[1]) for x in PACIENTES_DEMO}
        otros = [p for p in P.values() if p.rut not in fijos]
        hoy_cupos = list(Cupo.objects.filter(fecha=self.hoy, bloqueado=False).select_related("agenda")
                         .order_by("hora_inicio")[:7])
        for i, cupo in enumerate(hoy_cupos):
            tens = self.tens_de(cupo)
            estado = ["confirmada", "confirmada", "sin_respuesta", "confirmada", "cancelada", "confirmada", "agendada"][i]
            c = Cita.objects.create(cupo=cupo, paciente=otros[i], estado=estado, creada_por=tens, canal="telefono",
                                    recordatorio_enviado_en=timezone.now() - timedelta(days=2))
            if i in (0, 2):
                Asistencia.objects.create(cita=c, asistio=True, registrada_por=tens)
            elif i == 1:
                Asistencia.objects.create(cita=c, asistio=False, registrada_por=tens)

        # --- Mañana (próximo día hábil): avisos en todos los estados. Se usa la kinesióloga si
        # atiende ese día; si no, el primer profesional con horas suficientes (la demo funciona
        # cualquier día de la semana).
        horas = []
        for prof in [prof_kine] + [p for p in self.profs if p != prof_kine]:
            horas = [c for c in libres(prof, manana)]
            if len(horas) >= 6:
                horas = [c for c in horas if c.agenda.policlinico_id == horas[0].agenda.policlinico_id]
            if len(horas) >= 6:
                break
        self.tens_avisos = None
        if len(horas) >= 6:
            tens = self.tens_avisos = self.tens_de(horas[0])
            c1 = ag.agendar(pac(8765432), horas[0], tens, canal="telefono").citas[0]  # aviso falla (sin móvil ni correo)
            conf.enviar_recordatorio(c1, tens)
            c2 = ag.agendar(pac(9876543), horas[1], tens, canal="presencial").citas[0]
            conf.enviar_recordatorio(c2, tens)
            conf.registrar_confirmacion(c2, por_paciente=True)
            c3 = ag.agendar(pac(12345670), horas[3], tens, canal="whatsapp").citas[0]
            conf.enviar_recordatorio(c3, tens)
            conf.marcar_sin_respuesta(c3, tens)
            c4 = ag.agendar(pac(15234871), horas[5], tens, canal="telefono").citas[0]
            conf.enviar_recordatorio(c4, tens)
            conf.marcar_sin_respuesta(c4, tens)
            ag.agendar_sobrecupo(pac(16789012), c4.cupo, tens, observaciones="Sobrecupo de demostración")
            if len(horas) > 6:
                ag.agendar(pac(19876543), horas[6], tens, canal="presencial")  # aviso «por enviar»
        # Medicina general mañana y pasado: algunas citas agendadas (avisos pendientes)
        for prof in (self.profs[0], self.profs[1]):
            for fecha in (manana, proximo_habil(manana)):
                for cupo in libres(prof, fecha, 2):
                    try:
                        ag.agendar(self.rnd.choice(otros[10:]), cupo, self.tens_de(cupo),
                                   canal=self.rnd.choice(["telefono", "presencial"]))
                    except Exception:  # choque de horario del paciente aleatorio: se omite
                        pass

        # --- Reservas hechas por pacientes desde la web
        for cuerpo, prof in ((18765432, self.profs[6]), (26345678, self.profs[4])):
            fut = list(repo.cupos_libres({"desde": manana + timedelta(days=2), "hasta": manana + timedelta(days=14),
                                          "profesional": prof})[:1])
            if fut:
                ag.agendar_web(pac(cuerpo), fut[0])

        # --- RN-01: tratamientos con todas las sesiones de una vez
        for cuerpo, prof, n in ((24123456, self.profs[2], 4), (23456789, self.profs[5], 3)):
            fut = list(repo.cupos_libres({"desde": manana + timedelta(days=1), "hasta": manana + timedelta(days=10),
                                          "profesional": prof})[:1])
            if fut:
                ag.agendar(pac(cuerpo), fut[0], self.tens_de(fut[0]), sesiones=n, observaciones="Tratamiento completo")

        # --- Una cancelada por el paciente
        fut = list(repo.cupos_libres({"desde": manana + timedelta(days=3), "hasta": manana + timedelta(days=12),
                                      "profesional": self.profs[0]})[:1])
        if fut:
            c = ag.agendar(pac(6543219), fut[0], self.tens_de(fut[0])).citas[0]
            conf.registrar_cancelacion(c, motivo="El paciente avisó que estará fuera de Santiago", por_paciente=True)
        self.stdout.write(f"  Próximas citas: {Cita.objects.filter(cupo__fecha__gte=self.hoy).count()} · "
                          f"Avisos: {MensajeEnviado.objects.count()} · Próximo día hábil: {manana:%d/%m/%Y}")
        if self.tens_avisos:
            self.stdout.write(f"  Avisos del próximo día hábil en todos los estados: entrar como "
                              f"«{self.tens_avisos.username}» ({self.tens_avisos.policlinico_tens.nombre})")

    def cargar_proximos_dias(self, dias_habiles: int = 5, ocupacion: float = .5):
        """Ocupa cerca de la mitad de las horas libres de los próximos días hábiles (sin enviar avisos)."""
        fechas, d = [], self.hoy
        while len(fechas) < dias_habiles:
            d = proximo_habil(d)
            fechas.append(d)
        pacientes = list(Paciente.objects.all())
        ocupado = set(Cita.objects.filter(cupo__fecha__in=fechas, estado__in=Cita.VIGENTES)
                      .values_list("paciente_id", "cupo__fecha", "cupo__hora_inicio"))
        cupos = (Cupo.objects.filter(fecha__in=fechas, bloqueado=False).select_related("agenda")
                 .exclude(citas__estado__in=Cita.VIGENTES).order_by("fecha", "hora_inicio"))
        aviso_hasta = self.hoy + timedelta(days=settings.CITA_DIAS_AVISO_DEFECTO)
        citas = []
        for cupo in cupos:
            if self.rnd.random() > ocupacion:
                continue
            candidatos = [p for p in self.rnd.sample(pacientes, 8)
                          if (p.pk, cupo.fecha, cupo.hora_inicio) not in ocupado]
            if not candidatos:
                continue
            p = candidatos[0]
            ocupado.add((p.pk, cupo.fecha, cupo.hora_inicio))
            creada = timezone.now() - timedelta(days=self.rnd.randint(2, 15))
            datos = {"estado": "agendada"}
            if cupo.fecha <= aviso_hasta:  # ya se envió el recordatorio: algunos respondieron
                r = self.rnd.random()
                datos = {"estado": "confirmada" if r < .6 else ("sin_respuesta" if r < .75 else "agendada"),
                         "recordatorio_enviado_en": timezone.now() - timedelta(hours=self.rnd.randint(2, 30))}
                if datos["estado"] != "agendada":
                    datos["respuesta_origen"] = "" if datos["estado"] == "sin_respuesta" else \
                        self.rnd.choice(["paciente", "paciente", "tens"])
                    datos["respuesta_en"] = datos["recordatorio_enviado_en"] + timedelta(hours=3)
            citas.append(Cita(cupo=cupo, paciente=p, creada_por=self.tens_de(cupo), creada_en=creada,
                              canal=self.rnd.choice(["presencial", "telefono", "telefono", "whatsapp", "web"]), **datos))
        Cita.objects.bulk_create(citas)
        self.stdout.write(f"  Próximos {dias_habiles} días hábiles ({fechas[0]:%d/%m} al {fechas[-1]:%d/%m}): "
                          f"{len(citas)} citas más")

    def cargar_lista_espera(self):
        """Listas de espera por especialidad y policlínico (nunca por profesional)."""
        enf, kine, mg = self.esps["Enfermería"], self.esps["Kinesiología"], self.esps["Medicina General"]
        santa_rosa, san_lazaro, los_olivos = self.polis[1], self.polis[0], self.polis[2]
        fijos = {rut(x[1]) for x in PACIENTES_DEMO}
        otros = [p for p in Paciente.objects.order_by("pk") if p.rut not in fijos][20:]
        filas = [
            (otros[0], enf, santa_rosa, "en_espera", 15),
            (Paciente.objects.get(rut=rut(22456789)), enf, santa_rosa, "contactado", 12),
            (otros[1], enf, santa_rosa, "en_espera", 9), (otros[2], enf, santa_rosa, "sin_contacto", 8),
            (Paciente.objects.get(rut=rut(12345670)), kine, san_lazaro, "en_espera", 6),
            (otros[3], enf, los_olivos, "en_espera", 4),
            (otros[4], mg, san_lazaro, "en_espera", 3), (otros[5], kine, san_lazaro, "agendado", 2),
        ]
        for i, (p, esp, pol, estado, dias) in enumerate(filas, 1):
            SolicitudEspera.objects.create(
                paciente=p, especialidad=esp, policlinico=pol, estado=estado, orden=i,
                creada_por=None if i % 3 == 0 else self.tens_por_pol[pol.pk],
                canal="web" if i % 3 == 0 else "telefono", creada_en=timezone.now() - timedelta(days=dias),
                resultado_contacto="no_contesta" if estado == "sin_contacto" else "sin_resultado")
        self.stdout.write(f"  Lista de espera: {len(filas)} pacientes")

    def cargar_documentos(self, tens):
        p = Paciente.objects.get(rut=rut(22456789))  # sin inscripción CESFAM (RN-05)
        ahora = timezone.now()
        for tipo, nombre, tam, dias in (("fonasa", "certificado_fonasa.pdf", 184_320, 9),
                                        ("derivacion", "orden_derivacion.pdf", 225_280, 9),
                                        ("otro", "certificado_medico.jpg", 1_258_291, 8)):
            DocumentoPaciente.objects.create(paciente=p, tipo=tipo, nombre=nombre, tamano=tam, subido_por=tens,
                                             subido_en=ahora - timedelta(days=dias))
            OperacionDocumento.objects.create(paciente=p, usuario=tens, accion="adjunto",
                                              detalle=dict(DocumentoPaciente.Tipo.choices)[tipo],
                                              fecha=ahora - timedelta(days=dias))
        OperacionDocumento.objects.create(paciente=p, usuario=tens, accion="consulto", detalle="orden_derivacion.pdf",
                                          fecha=ahora - timedelta(days=1))
        self.stdout.write("  Documentos de ejemplo: 3")

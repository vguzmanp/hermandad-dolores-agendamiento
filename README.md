# Sistema de Gestión de Pacientes y Citas — Hermandad de Dolores

Proyecto de Ingeniería de Software (UDD). Aplicación web hecha en Django para agendar
horas en los policlínicos de la Hermandad de Dolores.

- Los pacientes reservan su hora desde la web, sin crear cuenta, y confirman, cancelan o
  cambian su hora desde el link que les llega por correo.
- Las TENS/TONS (un usuario por policlínico) agendan, confirman citas, manejan la lista
  de espera, bloquean horas y registran la asistencia.
- La Administración gestiona profesionales, horarios, policlínicos y reportes.

## Requisitos

- Python 3.11 o superior
- pip
- Git
- PostgreSQL (opcional; por defecto se usa SQLite)

## Instalación

En PowerShell:

```powershell
git clone https://github.com/vguzmanp/hermandad-dolores-agendamiento.git
cd hermandad-dolores-agendamiento
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py cargar_demo --reset
```

Si PowerShell no deja activar el entorno, ejecutar una vez:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## Configuración

La configuración está en el archivo `.env`.

**Base de datos.** Por defecto usa SQLite (`DB_ENGINE=sqlite`). Para usar PostgreSQL hay
que crear la base de datos, poner `DB_ENGINE=postgres`, completar `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `DB_HOST` y `DB_PORT`, y volver a ejecutar `migrate` y `cargar_demo --reset`.

**Correo.** Con `ENVIAR_CORREOS=False` los avisos solo quedan registrados en la pantalla
"Avisos enviados". Para enviarlos de verdad por Gmail:

1. Activar la verificación en 2 pasos en la cuenta de Gmail y crear una contraseña de
   aplicación.
2. En `.env`:
   ```
   ENVIAR_CORREOS=True
   EMAIL_HOST_USER=cuenta@gmail.com
   EMAIL_HOST_PASSWORD=contraseña-de-aplicación
   ```
3. Probar el envío: `python manage.py probar_correo destino@correo.cl`

Los links de los correos usan `SITIO_PUBLICO_URL` (por defecto `http://127.0.0.1:8000`).

## Ejecución

```powershell
.\venv\Scripts\Activate.ps1
python manage.py runserver
```

Abrir http://127.0.0.1:8000/. El inicio es el login del personal; los pacientes entran
desde el botón "Reservar una hora".

Las fechas de los datos de prueba se calculan desde el día en que se cargan, por lo que
conviene recargarlos el mismo día de la demostración. Si el envío de correos está activado,
desactivarlo durante la carga:

```powershell
$env:ENVIAR_CORREOS="False"; python manage.py cargar_demo --reset; Remove-Item Env:ENVIAR_CORREOS
```

## Usuarios de prueba

Contraseña: `demo1234`

| Usuario | Rol |
|---|---|
| `administracion` | Administración |
| `san_lazaro`, `santa_rosa`, `los_olivos`, `el_carmen`, `buen_samaritano`, `santa_clara`, `telemedicina` | TENS/TONS de cada policlínico |
| `admin` | Superusuario |

## Pruebas

```powershell
python manage.py test
```

Las pruebas obligatorias están en `citas/tests.py` (clase `PruebasObligatoriasRN02RN07`):
doble asignación rechazada, sobrecupo permitido con `sin_respuesta`, sobrecupo rechazado si
la cita está agendada o confirmada, segundo sobrecupo rechazado y cancelación que libera el cupo.

## Estructura

Una app por módulo, con capas vistas → services → repositorios → modelos:

```
config/         configuración y rutas
core/           roles, inicio y comando cargar_demo
pacientes/      pacientes, adulto responsable y documentos
profesionales/  policlínicos, especialidades y profesionales
agenda/         horario semanal, cupos y bloqueo de horas
citas/          citas, confirmación, sobrecupo y avisos
lista_espera/   lista de espera por especialidad y policlínico
asistencia/     asistencia
reportes/       reportes
portal/         reserva de horas para pacientes
templates/      plantillas comunes
static/         estilos y scripts
```

## Estado de los módulos

| Módulo | Estado |
|---|---|
| Login, roles y datos de prueba | Completo |
| Pacientes | Completo |
| Profesionales, policlínicos, especialidades, agendas y cupos | Completo |
| Citas | Completo |
| Asistencia | Completo |
| Lista de espera | Completo |
| Documentos | Completo |
| Reportes | Completo |
| Portal del paciente | Completo |
| Avisos por correo | Completo (Gmail) |
| Avisos por WhatsApp | Simulado: quedan registrados en "Avisos enviados" |

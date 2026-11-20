# Sistema de Gestión de Pacientes y Citas — Hermandad de Dolores

Proyecto de Ingeniería de Software (UDD). Aplicación web hecha en Django para agendar
horas en los policlínicos de la Hermandad de Dolores.

- Los pacientes reservan su hora desde la web, sin crear cuenta.
- Las TENS/TONS (un usuario por policlínico) agendan, confirman citas, manejan la lista
  de espera y registran la asistencia.
- La Administración gestiona profesionales, horarios y reportes.

## Requisitos

- Python 3.11 o superior
- pip
- Git
- PostgreSQL (opcional; por ahora se usa SQLite)

## Instalación

En PowerShell, dentro de la carpeta del proyecto:

```powershell
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

La configuración está en el archivo `.env`. Por defecto usa SQLite (`DB_ENGINE=sqlite`).
Para usar PostgreSQL hay que crear la base de datos, poner `DB_ENGINE=postgres`,
completar `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` y `DB_PORT`, y volver a ejecutar
`migrate` y `cargar_demo --reset`.

## Ejecución

```powershell
.\venv\Scripts\Activate.ps1
python manage.py runserver
```

Abrir http://127.0.0.1:8000/

Las fechas de los datos de prueba se calculan desde el día en que se cargan, por lo que
conviene ejecutar `python manage.py cargar_demo --reset` el mismo día de la demostración.

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

Una app por módulo, con capas vistas → services → modelos → repositorios:

```
core/           roles, inicio y comando cargar_demo
pacientes/      pacientes, adulto responsable y documentos
profesionales/  policlínicos, especialidades y profesionales
agenda/         horario semanal y cupos
citas/          citas, confirmación, sobrecupo y avisos
lista_espera/   lista de espera
asistencia/     asistencia
reportes/       reportes
portal/         reserva de horas para pacientes
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

Los avisos por WhatsApp y correo no están conectados a un servicio real: quedan
registrados en la pantalla "Avisos enviados".

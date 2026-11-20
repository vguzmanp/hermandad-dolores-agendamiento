# Sistema de Gestión de Pacientes y Citas — Hermandad de Dolores

MVP del proyecto de Ingeniería de Software (UDD). Aplicación web en Django,
organizada como monolito modular en capas, con interfaz en español (plantillas
Django + Bootstrap 5).

> **Nota sobre la base de datos:** el diseño apunta a **PostgreSQL**, pero en el
> equipo de desarrollo actual PostgreSQL no está instalado, así que **por ahora se
> usa SQLite** (`DB_ENGINE=sqlite` en `.env`). Para cambiar a PostgreSQL basta con
> configurar las variables `DB_*` (ver más abajo). En SQLite, `select_for_update`
> no bloquea filas (SQLite bloquea la base completa en cada escritura), así que las
> reglas RN-02/RN-07 se siguen cumpliendo. Además hay restricciones únicas
> parciales en la base de datos como respaldo.

## Requisitos

| Herramienta | Versión | Estado en el equipo de desarrollo |
|---|---|---|
| Python | 3.11 o superior | 3.13 ✅ |
| pip | incluido con Python | ✅ |
| Git | cualquiera reciente | ✅ |
| PostgreSQL | 14 o superior (opcional por ahora) | ❌ no instalado → SQLite |

Para instalar PostgreSQL en Windows: `winget install PostgreSQL.PostgreSQL.16` o el
instalador de https://www.postgresql.org/download/windows/.

No se necesita internet para la demo: Bootstrap viene incluido en `static/vendor/`.

## Instalación (Windows / PowerShell)

```powershell
cd C:\Users\<usuario>\Desktop\Final_IS
python -m venv venv
.\venv\Scripts\Activate.ps1          # si PowerShell lo bloquea: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
Copy-Item .env.example .env          # y edita los valores si hace falta
python manage.py migrate
python manage.py cargar_demo         # roles, usuarios de prueba y datos ficticios
```

En Linux/macOS: `source venv/bin/activate` y `cp .env.example .env`.

## Configuración (`.env`)

| Variable | Por defecto | Descripción |
|---|---|---|
| `DJANGO_SECRET_KEY` | (clave de desarrollo) | Clave secreta de Django. |
| `DJANGO_DEBUG` | `True` | Modo depuración. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Hosts permitidos. |
| `DB_ENGINE` | `sqlite` | `sqlite` o `postgres`. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | — | Conexión a PostgreSQL. |
| `MEDIA_DIR` | `media` | Carpeta de documentos subidos. |
| `CITA_DIAS_AVISO_DEFECTO` | `2` | `Cita.diasAviso` por defecto. |
| `AGENDA_SEMANAS_GENERACION` | `4` | Semanas de cupos que se generan por defecto. |

### Usar PostgreSQL

```powershell
# psql -U postgres -c "CREATE DATABASE hermandad_dolores;"
# En .env:  DB_ENGINE=postgres  DB_PASSWORD=<tu clave>
python manage.py migrate
python manage.py cargar_demo
```

## Ejecución

```powershell
.\venv\Scripts\Activate.ps1
python manage.py runserver
```

Abrir http://127.0.0.1:8000/

`python manage.py cargar_demo --reset` borra los datos de dominio y vuelve a crearlos.
Conviene correrlo el mismo día de la demo, porque los cupos y las citas se generan
a partir de la fecha actual.

## Usuarios de prueba

Contraseña de todos: **`demo1234`**

| Usuario | Rol | Qué puede hacer |
|---|---|---|
| `tens` | TENS/TONS | Pacientes, disponibilidad, agendar, sobrecupos, confirmar/cancelar, recordatorios, mensajes |
| `administracion` | Administración | Profesionales, especialidades, policlínicos, agendas (bloques), generar/bloquear/liberar cupos; consulta pacientes y citas |
| `profesional` | Profesional | Ve solo sus propias citas (Andrés Soto, Medicina General) y, en la etapa 6, estadísticas |
| `admin` | Superusuario | Todo, incluido el panel `/admin/` de Django |

## Pruebas

```powershell
python manage.py test
```

Pruebas obligatorias (en `citas/tests.py`, clase `PruebasObligatoriasRN02RN07`):

- doble asignación rechazada;
- sobrecupo permitido cuando la cita está `sin_respuesta`;
- sobrecupo rechazado si la cita está `agendada` o `confirmada`;
- segundo sobrecupo rechazado;
- la cancelación libera el cupo.

## Arquitectura

```
config/          settings (variables de entorno), urls
core/            roles (grupos), excepciones de dominio, plantillas base, comando cargar_demo
pacientes/       Paciente, AdultoResponsable            (RF-02, RN-03, RN-04, RN-05)
profesionales/   Policlinico, Especialidad, Profesional
agenda/          Agenda (bloque semanal), Cupo          (generar, bloquear, liberar)
citas/           Cita, AgendamientoService, ConfirmacionService,
                 ICitaRepository, CitaRepositoryPostgres, INotificador, NotificadorLog
lista_espera/    SolicitudEspera, ListaEsperaService    (etapa 6)
asistencia/      Asistencia, AsistenciaService          (etapa 5)
reportes/        ReporteService                         (etapa 6)
```

Cada módulo sigue las capas **vistas → services → modelos → repositorios**
(`views.py` → `services.py` → `models.py` / `repositories.py`). Los permisos por
rol se validan en las vistas y también en los servicios (`roles.exigir_rol`).

### Reglas de negocio clave

- **RN-01**: solo se agenda sobre cupos disponibles (no bloqueados, sin cita normal y
  con horario futuro). Si la especialidad lo permite, se agendan todas las sesiones de
  una vez (mismo profesional, policlínico y hora, en fechas siguientes), en una sola
  transacción: se agendan todas o ninguna.
- **RN-02 + RN-07**: `CitaRepositoryPostgres.crear_cita` / `crear_sobrecupo` corren dentro
  de `transaction.atomic()` con `select_for_update()` sobre el `Cupo`. Dentro de esa
  transacción se verifica que no haya otra cita normal; para un sobrecupo, que la cita
  original **siga** en `sin_respuesta` y que no exista otro sobrecupo (máximo 2 citas
  por cupo). Las restricciones únicas parciales de `Cita` respaldan la regla en la BD.
- **Cancelación**: la cita cancelada deja de ocupar el cupo, que queda libre. Si se
  cancela la cita normal y había un sobrecupo, el sobrecupo pasa a ser la cita normal.
- **WhatsApp no se integra**: `NotificadorLog` guarda los mensajes y los muestra en
  *Citas → Mensajes enviados*. La respuesta del paciente (confirma / cancela / no
  responde) se simula con botones en la interfaz.

## Estado de los módulos

| Módulo | Estado |
|---|---|
| Login, roles y `cargar_demo` | Completo |
| Pacientes (registro, búsqueda por RUT, adulto responsable) | Completo (falta documentos → etapa 6) |
| Profesionales, policlínicos, especialidades | Completo |
| Agendas y cupos | Completo |
| Citas (disponibilidad, agendar, sesiones, sobrecupo, confirmación, cancelación) | Completo |
| Asistencia | Pendiente (etapa 5) |
| Lista de espera | Pendiente (etapa 6) |
| Documentos del paciente | Pendiente (etapa 6) |
| Reportes y estadísticas | Pendiente (etapa 6) |

## Flujo sugerido para la demo

1. Entrar como `tens` → *Pacientes → Registrar*: buscar un RUT nuevo, registrar a un
   menor de edad (pide adulto responsable) y ver la advertencia de CESFAM.
2. *Citas → Disponibilidad*: filtrar por Kinesiología y agendar 4 sesiones de una vez.
3. Intentar agendar el mismo cupo de nuevo: el sistema lo rechaza (RN-02).
4. *Citas → Recordatorios*: enviar recordatorios; marcar uno como «No responde» y
   agendar un sobrecupo en ese cupo; intentar un segundo sobrecupo (rechazado).
5. Simular «Paciente cancela» y ver que el cupo vuelve a quedar libre.
6. *Mensajes enviados*: ver los mensajes simulados.
7. Entrar como `administracion` → *Agendas y cupos*: crear un bloque semanal, generar
   cupos, bloquear un cupo o un día y liberarlo.
8. Entrar como `profesional` → *Mis citas*.

# Sistema de Gestión de Pacientes y Citas — Hermandad de Dolores

MVP del proyecto de Ingeniería de Software (UDD). Aplicación web en Django,
organizada como monolito modular en capas, con interfaz en español basada en el
diseño de Figma (plantillas Django + Bootstrap 5, tipografía Inter incluida).

Tiene dos caras:

- **Portal del paciente (público, sin cuenta ni clave):** reservar una hora en 4 pasos,
  anotarse en la lista de espera si no hay horas, adjuntar FONASA/CESFAM y responder el
  aviso (confirmar, cambiar o cancelar) desde el link que recibe.
- **Sistema de gestión (con cuenta):** TENS/TONS, Administración y Profesional.

> **Nota sobre la base de datos:** el diseño apunta a **PostgreSQL**, pero en el equipo de
> desarrollo PostgreSQL no está instalado, así que **por ahora se usa SQLite**
> (`DB_ENGINE=sqlite` en `.env`). Para cambiar a PostgreSQL basta con configurar las
> variables `DB_*`. En SQLite, `select_for_update` no bloquea filas (SQLite bloquea la
> base completa en cada escritura), así que las reglas RN-02/RN-07 se siguen cumpliendo;
> además hay restricciones únicas parciales en la base de datos como respaldo.

## Requisitos

| Herramienta | Versión | Estado en el equipo de desarrollo |
|---|---|---|
| Python | 3.11 o superior | 3.13 ✅ |
| pip | incluido con Python | ✅ |
| Git | cualquiera reciente | ✅ |
| PostgreSQL | 14 o superior (opcional por ahora) | ❌ no instalado → SQLite |

Para instalar PostgreSQL en Windows: `winget install PostgreSQL.PostgreSQL.16` o el
instalador de https://www.postgresql.org/download/windows/.

No se necesita internet para la demo: Bootstrap y la tipografía vienen en `static/vendor/`.

## Instalación (Windows / PowerShell)

```powershell
cd C:\Users\<usuario>\Desktop\Final_IS
python -m venv venv
.\venv\Scripts\Activate.ps1          # si PowerShell lo bloquea: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
Copy-Item .env.example .env          # y edita los valores si hace falta
python manage.py migrate
python manage.py cargar_demo --reset # roles, usuarios de prueba y datos ficticios
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
| `MEDIA_DIR` | `media` | Carpeta de documentos subidos (subida local). |
| `DOCUMENTO_MAX_MB` | `10` | Tamaño máximo de un documento. |
| `CITA_DIAS_AVISO_DEFECTO` | `2` | `Cita.diasAviso` por defecto. |
| `AGENDA_SEMANAS_GENERACION` | `4` | Semanas de cupos que se generan desde un bloque semanal. |
| `SITIO_PUBLICO_URL` | `http://127.0.0.1:8000` | Base del link que llega en los avisos (`/c/<código>/`). |

### Usar PostgreSQL

```powershell
# psql -U postgres -c "CREATE DATABASE hermandad_dolores;"
# En .env:  DB_ENGINE=postgres  DB_PASSWORD=<tu clave>
python manage.py migrate
python manage.py cargar_demo --reset
```

## Ejecución

```powershell
.\venv\Scripts\Activate.ps1
python manage.py cargar_demo --reset   # recomendado el mismo día de la demo (las fechas son relativas a hoy)
python manage.py runserver
```

Abrir http://127.0.0.1:8000/ → «¿Cómo quieres entrar?» (Paciente / TENS / Administración).

## Usuarios de prueba

Contraseña de todos: **`demo1234`**. Los pacientes **no** tienen cuenta.

| Usuario | Rol | Qué puede hacer |
|---|---|---|
| `tens` | TENS/TONS | Inicio con avisos del próximo día hábil, agendar (calendario, sesiones, sobrecupo, reagendar), pacientes, documentos, lista de espera (gestionar y subir), calendario de profesionales (bloquear/liberar horas), asistencia, avisos enviados |
| `administracion` | Administración | Inicio con indicadores de 14 días, profesionales (equipo, horario semanal, bloquear/liberar), especialidades y policlínicos, lista de espera (solo consulta), reportes con CSV, documentos |
| `profesional` | Profesional | Sus citas del día, «Mis citas» y sus estadísticas (Dr. Andrés Soto, Medicina General) |
| `admin` | Superusuario | Todo, incluido `/admin/` de Django |

## Pruebas

```powershell
python manage.py test
```

79 pruebas. Las obligatorias están en `citas/tests.py`, clase `PruebasObligatoriasRN02RN07`:

- doble asignación rechazada;
- sobrecupo permitido cuando la cita está `sin_respuesta`;
- sobrecupo rechazado si la cita está `agendada` o `confirmada`;
- segundo sobrecupo rechazado;
- la cancelación libera el cupo.

Además: RUT y pacientes, agendas y cupos, reagendar con rollback, avisos con falla, portal
del paciente (reserva, paciente nuevo con adulto responsable, hora tomada mientras se
reservaba, lista de espera, confirmar/cancelar/cambiar por link), asistencia, lista de
espera (orden de llegada y «subir»), documentos (RN-05 e historial) y reportes.

## Arquitectura

```
config/          settings (variables de entorno), urls
core/            roles (grupos), excepciones de dominio, layout, inicio por rol, cargar_demo
pacientes/       Paciente, AdultoResponsable, DocumentoPaciente (+ historial de operaciones)
profesionales/   Policlinico, Especialidad, Profesional
agenda/          Agenda (bloque semanal), Cupo · horario semanal y calendario bloquear/liberar
citas/           Cita, AgendamientoService, ConfirmacionService, ICitaRepository,
                 CitaRepositoryPostgres, INotificador, NotificadorLog
lista_espera/    SolicitudEspera, ListaEsperaService
asistencia/      Asistencia, AsistenciaService
reportes/        ReporteService (caracterización; demanda por profesional y policlínico; CSV)
portal/          portal público del paciente (solo vistas: usa los servicios de los módulos)
```

Cada módulo sigue las capas **vistas → services → modelos → repositorios**. Los permisos
por rol se validan en las vistas y también en los servicios (`roles.exigir_rol`).

**Especialidad y policlínico son conceptos distintos**: la especialidad es el tipo de
atención (Kinesiología); el policlínico es el lugar (6 policlínicos + Telemedicina). Un
profesional tiene una especialidad y atiende en uno o más policlínicos según su Agenda.

### Reglas de negocio clave

- **RN-01**: solo se agenda sobre cupos disponibles (no bloqueados, sin cita normal, horario
  futuro, profesional activo). Si la especialidad lo permite, la TENS agenda todas las
  sesiones de una vez (mismo profesional, policlínico y hora): todas o ninguna.
- **RN-02 + RN-07**: `CitaRepositoryPostgres.crear_cita` / `crear_sobrecupo` corren dentro de
  `transaction.atomic()` con `select_for_update()` sobre el `Cupo`, verificando en la misma
  transacción que no haya otra cita normal; para un sobrecupo, que la cita original **siga**
  en `sin_respuesta` y que no exista otro sobrecupo (máximo 2 citas por cupo).
- **Cancelación**: la cita cancelada deja de ocupar el cupo, que queda libre. Si se cancela la
  cita normal y había un sobrecupo, el sobrecupo pasa a ser la cita normal.
- **Reagendar / cambiar hora**: en una transacción se cancela la cita actual y se crea la
  nueva; si la nueva hora ya no está disponible, no cambia nada.
- **Quién agenda**: las TENS/TONS (presencial, teléfono o WhatsApp) y el propio paciente desde
  el portal web (`canal = web`, sin usuario). Los sobrecupos solo los agenda la TENS.
- **RN-03/RN-04/RN-05**: correo opcional; adulto responsable obligatorio para menores o
  dependientes (los avisos le llegan a él/ella); si falta la inscripción CESFAM se advierte,
  y al adjuntar el comprobante queda resuelto.
- **RN-06**: lista de espera por orden de llegada; la TENS puede «subir» a un paciente un lugar.
  Al agendarle una cita, su solicitud pasa a «Agendado».
- **Avisos**: WhatsApp y correo no se integran. `NotificadorLog` guarda cada aviso (pantalla
  *Avisos enviados*). El WhatsApp se marca «No se pudo enviar» si el celular no es un móvil
  chileno válido (para demostrar «Reintentar aviso»). La respuesta del paciente se hace desde
  el link `/c/<código>/` o la registra la TENS («Registrar respuesta»).
- **Bloquear y liberar horas**: lo pueden hacer TENS y Administración (como en el diseño); el
  horario semanal solo lo define la Administración. Un cupo con cita no se bloquea.

## Estado de los módulos

| Módulo | Estado |
|---|---|
| Login, roles y `cargar_demo` | Completo |
| Portal del paciente (reserva, lista de espera, aviso, confirmar/cambiar/cancelar) | Completo (WhatsApp y correo simulados) |
| Pacientes (registro, búsqueda, adulto responsable) | Completo |
| Profesionales, especialidades y policlínicos | Completo |
| Agendas y cupos (horario semanal, calendario bloquear/liberar) | Completo |
| Citas (calendario, sesiones, sobrecupo, reagendar, avisos, respuestas) | Completo |
| Asistencia | Completo |
| Lista de espera | Completo |
| Documentos (subida local + historial) | Completo |
| Reportes (caracterización, demanda por profesional y policlínico, CSV) | Completo (variables de caracterización por validar, RF-14) |

## Flujo sugerido para la demo

1. **Portada** → *Reservar hora* (paciente): Kinesiología → elegir día y hora → RUT nuevo
   (menor de edad, pide adulto responsable) → confirmar → *Ver aviso de confirmación* →
   abrir el link → *Sí, asistiré* / *Cambiar hora* / *Cancelar hora*.
2. Reservar **Enfermería**: no hay horas → *Anotarme en lista de espera*.
3. Entrar como `tens`: el inicio muestra los avisos del próximo día hábil (uno «No se pudo
   enviar» → *Reintentar aviso*; *Registrar respuesta*; *simular el envío de los avisos*).
4. *Citas*: buscar paciente, elegir especialidad/profesional, día en el calendario, hora;
   sobrecupo en una hora «sin respuesta»; intentar un segundo sobrecupo (rechazado); reagendar
   y cancelar desde «Citas del paciente».
5. *Pacientes*, *Documentos* (falta CESFAM → adjuntar), *Lista de espera* (gestionar, subir,
   agendar), *Profesionales* (bloquear y liberar de a poco), *Asistencia* (asistió / no asistió).
6. Entrar como `administracion`: alerta de la profesional sin horas con lista de espera,
   *Profesionales* (agregar, horario semanal, bloque que se cruza → error), *Reportes* + CSV.
7. Entrar como `profesional`: sus citas y estadísticas.

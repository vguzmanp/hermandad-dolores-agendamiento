"""
ReporteService: caracterización de pacientes, demanda y atención, y reporte de
pacientes con su historial. Todos los reportes aceptan los mismos filtros
combinables (período, policlínico, especialidad, profesional, estado de la cita,
asistencia, canal, sobrecupo y datos del paciente).
"""
import csv
import io
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db.models import Count, Exists, F, Max, Min, OuterRef, Q
from django.utils import timezone

from citas.models import Cita
from core.fechas import MESES_CORTOS
from pacientes.models import Paciente

from .forms import TRAMOS_EDAD

MESES_PERIODO = {"1m": 1, "3m": 3, "6m": 6, "12m": 12}


@dataclass
class Filtros:
    desde: date | None
    hasta: date | None
    etiqueta: str
    policlinico: object = None
    especialidad: object = None
    profesional: object = None
    estado: str = ""
    asistencia: str = ""
    canal: str = ""
    sobrecupo: str = ""
    sexo: str = ""
    edad: str = ""
    nacionalidad: str = ""
    cesfam: str = ""
    responsable: str = ""
    extra: dict = field(default_factory=dict)  # filtros propios del reporte de pacientes

    @property
    def activos(self) -> list[str]:
        """Descripción corta de los filtros aplicados (para el encabezado del reporte)."""
        res = []
        for etiqueta, valor in (("Policlínico", self.policlinico), ("Especialidad", self.especialidad),
                                ("Profesional", self.profesional and self.profesional.nombre)):
            if valor:
                res.append(f"{etiqueta}: {valor}")
        textos = {
            "estado": dict(Cita.Estado.choices), "canal": dict(Cita.Canal.choices),
            "asistencia": {"asistio": "Asistió", "no_asistio": "No asistió", "sin_registro": "Sin registro"},
            "sexo": dict(Paciente.Sexo.choices), "edad": {k: t for k, t, _, _ in TRAMOS_EDAD},
        }
        for campo, nombre in (("estado", "Estado"), ("asistencia", "Asistencia"), ("canal", "Canal"),
                              ("sexo", "Sexo"), ("edad", "Edad")):
            v = getattr(self, campo)
            if v:
                res.append(f"{nombre}: {textos[campo].get(v, v)}")
        if self.nacionalidad:
            res.append(f"Nacionalidad: {self.nacionalidad}")
        for campo, nombre in (("sobrecupo", "Sobrecupo"), ("cesfam", "CESFAM"), ("responsable", "Adulto responsable")):
            v = getattr(self, campo)
            if v:
                res.append(f"{nombre}: {'sí' if v == 'si' else 'no'}")
        return res


def _restar_meses(d: date, meses: int) -> date:
    m = d.month - meses
    a = d.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    return date(a, m, 1)


def _restar_anios(d: date, anios: int) -> date:
    try:
        return d.replace(year=d.year - anios)
    except ValueError:  # 29 de febrero
        return d.replace(year=d.year - anios, day=28)


def _etiqueta(desde, hasta) -> str:
    if desde is None and hasta is None:
        return "Todo el historial"
    if desde is None:
        return f"Hasta el {hasta:%d/%m/%Y}"
    if hasta is None:
        return f"Desde el {desde:%d/%m/%Y}"
    if desde.day == 1 and (desde.year, desde.month) != (hasta.year, hasta.month):
        return (f"{MESES_CORTOS[desde.month - 1].capitalize()} {desde.year}–"
                f"{MESES_CORTOS[hasta.month - 1].capitalize()} {hasta.year}")
    return f"{desde:%d/%m/%Y} – {hasta:%d/%m/%Y}"


def construir_filtros(datos: dict | None = None, hoy: date | None = None) -> Filtros:
    """Crea los filtros desde el cleaned_data del formulario (o valores por defecto)."""
    d = datos or {}
    hoy = hoy or timezone.localdate()
    periodo = d.get("periodo") or "3m"
    if periodo == "rango":
        desde, hasta = d.get("desde"), d.get("hasta")
    elif periodo == "todo":
        desde, hasta = None, None
    else:
        desde, hasta = _restar_meses(hoy, MESES_PERIODO.get(periodo, 3) - 1), hoy
    campos = {k: d.get(k) or "" for k in ("estado", "asistencia", "canal", "sobrecupo", "sexo", "edad",
                                            "nacionalidad", "cesfam", "responsable")}
    extra = {k: d.get(k) for k in ("q", "en_espera", "con_inasistencias", "sin_citas", "orden") if k in d}
    return Filtros(desde, hasta, _etiqueta(desde, hasta), d.get("policlinico"), d.get("especialidad"),
                   d.get("profesional"), extra=extra, **campos)


def _pct(parte, total) -> float:
    return round(100 * parte / total, 1) if total else 0.0


# --------------------------------------------------------------- filtros Q
def q_citas(f: Filtros, prefijo: str = "", periodo: bool = True) -> Q:
    """Condiciones sobre la cita. `prefijo` = 'citas__' para filtrar desde Paciente."""
    p = prefijo
    q = Q()
    if periodo and f.desde:
        q &= Q(**{f"{p}cupo__fecha__gte": f.desde})
    if periodo and f.hasta:
        q &= Q(**{f"{p}cupo__fecha__lte": f.hasta})
    if f.policlinico:
        q &= Q(**{f"{p}cupo__agenda__policlinico": f.policlinico})
    if f.especialidad:
        q &= Q(**{f"{p}cupo__agenda__profesional__especialidad": f.especialidad})
    if f.profesional:
        q &= Q(**{f"{p}cupo__agenda__profesional": f.profesional})
    if f.estado:
        q &= Q(**{f"{p}estado": f.estado})
    if f.canal:
        q &= Q(**{f"{p}canal": f.canal})
    if f.sobrecupo:
        q &= Q(**{f"{p}es_sobrecupo": f.sobrecupo == "si"})
    if f.asistencia == "asistio":
        q &= Q(**{f"{p}asistencia__asistio": True})
    elif f.asistencia == "no_asistio":
        q &= Q(**{f"{p}asistencia__asistio": False})
    elif f.asistencia == "sin_registro":
        q &= Q(**{f"{p}asistencia__isnull": True})
    return q


def q_paciente(f: Filtros, prefijo: str = "", hoy: date | None = None) -> Q:
    """Condiciones sobre el paciente. `prefijo` = 'paciente__' para filtrar desde Cita."""
    p = prefijo
    hoy = hoy or timezone.localdate()
    q = Q()
    if f.sexo:
        q &= Q(**{f"{p}sexo": f.sexo})
    if f.nacionalidad:
        q &= Q(**{f"{p}nacionalidad": f.nacionalidad})
    if f.cesfam:
        q &= Q(**{f"{p}inscrito_cesfam": f.cesfam == "si"})
    if f.responsable:
        q &= Q(**{f"{p}adulto_responsable__isnull": f.responsable != "si"})
    tramo = next(((a, b) for k, _, a, b in TRAMOS_EDAD if k == f.edad), None)
    if tramo:
        a, b = tramo
        # edad entre a y b  <=>  nacido entre (hoy - (b+1) años, hoy - a años]
        q &= Q(**{f"{p}fecha_nacimiento__gt": _restar_anios(hoy, b + 1),
                  f"{p}fecha_nacimiento__lte": _restar_anios(hoy, a)})
    return q


class ReporteService:
    def citas(self, f: Filtros):
        return (Cita.objects.filter(q_citas(f) & q_paciente(f, "paciente__"))
                .select_related("paciente", "paciente__adulto_responsable", "asistencia",
                                "cupo__agenda__profesional__especialidad", "cupo__agenda__policlinico")
                .distinct())

    @staticmethod
    def _asistencia(citas):
        asistio = [c for c in citas if c.asistencia_registrada and c.asistencia_registrada.asistio]
        no_asistio = [c for c in citas if c.asistencia_registrada and not c.asistencia_registrada.asistio]
        return asistio, no_asistio

    @staticmethod
    def _barras(contador: Counter, orden=None, maximo_items=None) -> list[dict]:
        items = [(k, contador.get(k, 0)) for k in orden] if orden else contador.most_common()
        if maximo_items and len(items) > maximo_items:
            items = items[:maximo_items - 1] + [("Otras", sum(v for _, v in items[maximo_items - 1:]))]
        tope = max((v for _, v in items), default=0) or 1
        return [{"nombre": k, "n": v, "ancho": round(100 * v / tope)} for k, v in items]

    # ----------------------------------------------------- caracterización
    def caracterizacion(self, f: Filtros) -> dict:
        citas = list(self.citas(f))
        vigentes = [c for c in citas if c.estado != Cita.Estado.CANCELADA or f.estado == Cita.Estado.CANCELADA]
        asistio, no_asistio = self._asistencia(citas)
        pacientes = list({c.paciente_id: c.paciente for c in vigentes}.values())
        atendidos = {c.paciente_id for c in asistio}
        n = len(pacientes)
        menores = sum(1 for p in pacientes if p.edad < 18)
        sexo = Counter(p.get_sexo_display() for p in pacientes)
        edades = Counter()
        for p in pacientes:
            for _, nombre, a, b in TRAMOS_EDAD:
                if a <= p.edad <= b:
                    edades[nombre] += 1
        por_mes = defaultdict(lambda: [0, 0])
        for c in asistio + no_asistio:
            por_mes[(c.cupo.fecha.year, c.cupo.fecha.month)][0 if c.asistencia_registrada.asistio else 1] += 1
        meses = []
        if por_mes:
            inicio = f.desde or date(*min(por_mes), 1)
            fin = f.hasta or timezone.localdate()
            d = date(inicio.year, inicio.month, 1)
            while d <= fin:
                a, na = por_mes[(d.year, d.month)]
                meses.append({"mes": f"{MESES_CORTOS[d.month - 1].capitalize()}{'' if d.year == fin.year else ' ' + str(d.year)[2:]}",
                              "pct": round(_pct(na, a + na)), "n": a + na})
                d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
        especialidades = Counter()
        for pid, esp in {(c.paciente_id, c.cupo.agenda.profesional.especialidad.nombre) for c in vigentes}:
            especialidades[esp] += 1
        return {
            "pacientes": n,
            "atendidos": len(atendidos),
            "adultos": n - menores, "ninos": menores,
            "inasistencia": _pct(len(no_asistio), len(asistio) + len(no_asistio)),
            "mujeres": round(_pct(sum(1 for p in pacientes if p.sexo == "F"), n)),
            "hombres": round(_pct(sum(1 for p in pacientes if p.sexo == "M"), n)),
            "cesfam": round(_pct(sum(1 for p in pacientes if p.inscrito_cesfam), n)),
            "con_responsable": sum(1 for p in pacientes if hasattr(p, "adulto_responsable")),
            "sexo": self._barras(sexo),
            "edades": self._barras(edades, [t for _, t, _, _ in TRAMOS_EDAD]),
            "nacionalidades": self._barras(Counter(p.nacionalidad for p in pacientes), maximo_items=5),
            "especialidades": self._barras(especialidades),
            "meses": meses,
            "max_mes": max((m["pct"] for m in meses), default=0) or 1,
        }

    # ------------------------------------------------- demanda y atención
    def demanda(self, f: Filtros) -> dict:
        citas = list(self.citas(f))
        grupos = {"prof": {}, "pol": {}, "esp": {}}
        for c in citas:
            prof, pol = c.cupo.agenda.profesional, c.cupo.agenda.policlinico
            esp = prof.especialidad
            for clave, pk, base in (("prof", prof.pk, {"nombre": prof.nombre, "detalle": esp.nombre, "pols": set()}),
                                    ("pol", pol.pk, {"nombre": pol.nombre, "detalle": ""}),
                                    ("esp", esp.pk, {"nombre": esp.nombre, "detalle": ""})):
                fila = grupos[clave].setdefault(pk, {**base, "pedidas": 0, "atenciones": 0, "inasistencias": 0,
                                                     "canceladas": 0, "sobrecupos": 0, "pacientes": set()})
                fila["pedidas"] += 1
                fila["pacientes"].add(c.paciente_id)
                fila["canceladas"] += c.estado == Cita.Estado.CANCELADA
                fila["sobrecupos"] += c.es_sobrecupo
                a = c.asistencia_registrada
                if a and a.asistio:
                    fila["atenciones"] += 1
                elif a:
                    fila["inasistencias"] += 1
            grupos["prof"][prof.pk]["pols"].add(pol.nombre)
        for dic in grupos.values():
            for fila in dic.values():
                fila["inasistencia"] = round(_pct(fila["inasistencias"], fila["atenciones"] + fila["inasistencias"]))
                fila["pacientes"] = len(fila["pacientes"])
                if "pols" in fila:
                    fila["policlinicos"] = ", ".join(sorted(fila.pop("pols")))
        asistio, no_asistio = self._asistencia(citas)
        estados = Counter(c.get_estado_display() for c in citas)
        canales = Counter(c.get_canal_display() for c in citas)
        orden = lambda d: sorted(d.values(), key=lambda x: (-x["pedidas"], x["nombre"]))  # noqa: E731
        return {
            "pedidas": len(citas),
            "pacientes": len({c.paciente_id for c in citas}),
            "atenciones": len(asistio),
            "canceladas": sum(1 for c in citas if c.estado == Cita.Estado.CANCELADA),
            "sobrecupos": sum(1 for c in citas if c.es_sobrecupo),
            "inasistencia": _pct(len(no_asistio), len(asistio) + len(no_asistio)),
            "por_profesional": orden(grupos["prof"]),
            "por_policlinico": orden(grupos["pol"]),
            "por_especialidad": orden(grupos["esp"]),
            "por_estado": self._barras(estados, [e.label for e in Cita.Estado]),
            "por_canal": self._barras(canales),
        }

    def csv_demanda(self, f: Filtros) -> str:
        d = self.demanda(f)
        salida = io.StringIO()
        w = csv.writer(salida, delimiter=";")
        w.writerow([f"Período: {f.etiqueta}"] + f.activos)
        cab = ["Horas pedidas", "Pacientes", "Atenciones", "Inasistencias", "Inasistencia %", "Canceladas", "Sobrecupos"]

        def fila(x):
            return [x["pedidas"], x["pacientes"], x["atenciones"], x["inasistencias"], x["inasistencia"],
                    x["canceladas"], x["sobrecupos"]]

        w.writerow([])
        w.writerow(["Profesional", "Especialidad", "Policlínico(s)"] + cab)
        for x in d["por_profesional"]:
            w.writerow([x["nombre"], x["detalle"], x["policlinicos"]] + fila(x))
        for titulo, clave in (("Policlínico", "por_policlinico"), ("Especialidad", "por_especialidad")):
            w.writerow([])
            w.writerow([titulo, "", ""] + cab)
            for x in d[clave]:
                w.writerow([x["nombre"], "", ""] + fila(x))
        return "﻿" + salida.getvalue()  # BOM para que Excel lea bien los acentos

    # --------------------------------------------------------- pacientes
    def pacientes(self, f: Filtros, hoy: date | None = None):
        """Pacientes con sus totales de citas en el período y según los filtros."""
        from lista_espera.models import SolicitudEspera

        hoy = hoy or timezone.localdate()
        en_cita = q_citas(f, "citas__")
        qs = (Paciente.objects.filter(q_paciente(f, hoy=hoy)).select_related("adulto_responsable")
              .annotate(
                  n_citas=Count("citas", filter=en_cita, distinct=True),
                  n_asistidas=Count("citas", filter=en_cita & Q(citas__asistencia__asistio=True), distinct=True),
                  n_inasistencias=Count("citas", filter=en_cita & Q(citas__asistencia__asistio=False), distinct=True),
                  n_canceladas=Count("citas", filter=en_cita & Q(citas__estado=Cita.Estado.CANCELADA), distinct=True),
                  ultima_atencion=Max("citas__cupo__fecha", filter=Q(citas__asistencia__asistio=True)),
                  proxima_cita=Min("citas__cupo__fecha", filter=Q(citas__cupo__fecha__gte=hoy,
                                                                  citas__estado__in=Cita.VIGENTES)),
                  en_espera=Exists(SolicitudEspera.objects.filter(paciente=OuterRef("pk"),
                                                                  estado__in=SolicitudEspera.ACTIVOS)),
              ))
        x = f.extra
        texto = (x.get("q") or "").strip()
        if texto:
            limpio = texto.replace(".", "").replace(" ", "")
            qs = qs.filter(Q(nombre__icontains=texto) | Q(rut__icontains=limpio))
        if not x.get("sin_citas"):
            qs = qs.filter(n_citas__gt=0)
        if x.get("en_espera"):
            qs = qs.filter(en_espera=x["en_espera"] == "si")
        if x.get("con_inasistencias") == "si":
            qs = qs.filter(n_inasistencias__gt=0)
        elif x.get("con_inasistencias") == "no":
            qs = qs.filter(n_inasistencias=0)
        orden = x.get("orden") or "nombre"
        campo = orden.lstrip("-")
        if campo in ("ultima_atencion", "proxima_cita"):  # los pacientes sin fecha van al final
            expr = F(campo).desc(nulls_last=True) if orden.startswith("-") else F(campo).asc(nulls_last=True)
            return qs.order_by(expr, "nombre")
        return qs.order_by(orden, "nombre")

    def resumen_pacientes(self, qs) -> dict:
        filas = list(qs.values("n_citas", "n_asistidas", "n_inasistencias", "n_canceladas", "en_espera"))
        asist = sum(r["n_asistidas"] for r in filas)
        inas = sum(r["n_inasistencias"] for r in filas)
        return {
            "pacientes": len(filas), "citas": sum(r["n_citas"] for r in filas), "asistidas": asist,
            "inasistencias": inas, "canceladas": sum(r["n_canceladas"] for r in filas),
            "en_espera": sum(1 for r in filas if r["en_espera"]), "inasistencia": _pct(inas, asist + inas),
        }

    def csv_pacientes(self, f: Filtros) -> str:
        salida = io.StringIO()
        w = csv.writer(salida, delimiter=";")
        w.writerow([f"Período: {f.etiqueta}"] + f.activos)
        w.writerow([])
        w.writerow(["Nombre", "RUT", "Edad", "Sexo", "Nacionalidad", "Celular", "Correo", "Inscrito CESFAM",
                    "Adulto responsable", "Citas", "Asistidas", "Inasistencias", "Canceladas", "Última atención",
                    "Próxima cita", "En lista de espera"])
        for p in self.pacientes(f):
            resp = getattr(p, "adulto_responsable", None)
            w.writerow([p.nombre, p.rut_formateado, p.edad, p.get_sexo_display(), p.nacionalidad, p.celular, p.correo,
                        "Sí" if p.inscrito_cesfam else "No", f"{resp.nombre} ({resp.parentesco})" if resp else "",
                        p.n_citas, p.n_asistidas, p.n_inasistencias, p.n_canceladas,
                        p.ultima_atencion.strftime("%d/%m/%Y") if p.ultima_atencion else "",
                        p.proxima_cita.strftime("%d/%m/%Y") if p.proxima_cita else "",
                        "Sí" if p.en_espera else "No"])
        return "﻿" + salida.getvalue()

    # ----------------------------------------------- historial de un paciente
    def historial(self, paciente: Paciente, f: Filtros) -> dict:
        """Ficha, citas (según los filtros de la cita), asistencia, lista de espera, documentos y avisos."""
        from lista_espera.models import SolicitudEspera

        todas = (Cita.objects.filter(paciente=paciente)
                 .select_related("asistencia", "cupo__agenda__profesional__especialidad", "cupo__agenda__policlinico",
                                 "creada_por", "cancelada_por")
                 .prefetch_related("mensajes"))
        citas = list(todas.filter(q_citas(f)).order_by("-cupo__fecha", "-cupo__hora_inicio"))
        asistio, no_asistio = self._asistencia(citas)
        hoy = timezone.localdate()
        historicas = list(todas)
        return {
            "citas": citas,
            "kpi": {
                "total": len(citas), "asistidas": len(asistio), "inasistencias": len(no_asistio),
                "canceladas": sum(1 for c in citas if c.estado == Cita.Estado.CANCELADA),
                "sobrecupos": sum(1 for c in citas if c.es_sobrecupo),
                "proximas": sum(1 for c in citas if c.cupo.fecha >= hoy and c.es_vigente),
                "inasistencia": _pct(len(no_asistio), len(asistio) + len(no_asistio)),
            },
            "total_historico": len(historicas),
            "primera_cita": min((c.cupo.fecha for c in historicas), default=None),
            "especialidades": self._barras(Counter(c.cupo.agenda.profesional.especialidad.nombre for c in citas)),
            "espera": list(SolicitudEspera.objects.filter(paciente=paciente)
                           .select_related("especialidad", "policlinico", "cita__cupo").order_by("-creada_en")),
            "documentos": list(paciente.documentos.select_related("subido_por")),
            "n_avisos": paciente.mensajes.count(),
        }

    def csv_historial(self, paciente: Paciente, f: Filtros) -> str:
        datos = self.historial(paciente, f)
        salida = io.StringIO()
        w = csv.writer(salida, delimiter=";")
        w.writerow([paciente.nombre, paciente.rut_formateado, f"Período: {f.etiqueta}"] + f.activos)
        w.writerow([])
        w.writerow(["Fecha", "Hora", "Especialidad", "Profesional", "Policlínico", "Canal", "Estado", "Sobrecupo",
                    "Asistencia", "Respuesta registrada por", "Observaciones", "Motivo de cancelación"])
        for c in datos["citas"]:
            a = c.asistencia_registrada
            w.writerow([c.cupo.fecha.strftime("%d/%m/%Y"), c.cupo.hora_inicio.strftime("%H:%M"),
                        c.cupo.agenda.profesional.especialidad.nombre, c.cupo.agenda.profesional.nombre,
                        c.cupo.agenda.policlinico.nombre, c.get_canal_display(), c.get_estado_display(),
                        "Sí" if c.es_sobrecupo else "No", ("Asistió" if a.asistio else "No asistió") if a else "",
                        c.get_respuesta_origen_display() if c.respuesta_origen else "", c.observaciones,
                        c.motivo_cancelacion])
        return "﻿" + salida.getvalue()


def indicadores_admin(hoy: date | None = None, dias: int = 14) -> dict:
    """Resumen de agendas para el inicio de Administración (próximos 14 días)."""
    from agenda.models import Cupo
    from lista_espera.models import SolicitudEspera
    from profesionales.models import Especialidad, Policlinico, Profesional

    hoy = hoy or timezone.localdate()
    hasta = hoy + timedelta(days=dias - 1)
    cupos = (Cupo.objects.filter(fecha__range=(hoy, hasta), agenda__activa=True, agenda__profesional__activo=True)
             .select_related("agenda__profesional__especialidad").prefetch_related("citas"))
    # lista de espera por (especialidad, policlínico)
    espera = Counter(SolicitudEspera.objects.filter(estado__in=SolicitudEspera.ACTIVOS)
                     .values_list("especialidad_id", "policlinico_id"))
    filas = {}
    for p in Profesional.objects.filter(activo=True).select_related("especialidad"):
        filas[p.pk] = {"profesional": p, "ofrecidos": 0, "con_cita": 0, "bloqueados": 0, "disponibles": 0}
    for c in cupos:
        f = filas.get(c.agenda.profesional_id)
        if f is None:
            continue
        f["ofrecidos"] += 1
        if c.bloqueado:
            f["bloqueados"] += 1
        elif c.citas_vigentes:
            f["con_cita"] += 1
        else:
            f["disponibles"] += 1
    filas = [f for f in filas.values() if f["ofrecidos"]] + [f for f in filas.values() if not f["ofrecidos"]]
    esps = Especialidad.objects.in_bulk([e for e, _ in espera])
    pols = Policlinico.objects.in_bulk([p for _, p in espera])
    espera_filas = sorted(({"especialidad": esps[e], "policlinico": pols[p], "pacientes": n}
                           for (e, p), n in espera.items()),
                          key=lambda x: (-x["pacientes"], x["policlinico"].nombre, x["especialidad"].nombre))
    abiertos = sum(f["ofrecidos"] - f["bloqueados"] for f in filas)
    con_cita = sum(f["con_cita"] for f in filas)
    return {
        "profesionales_activos": len(filas),
        "cupos_ofrecidos": sum(f["ofrecidos"] for f in filas),
        "ocupacion": round(_pct(con_cita, abiertos)),
        "en_espera": sum(espera.values()),
        "filas": filas,
        "espera_filas": espera_filas,
        "dias": dias,
    }

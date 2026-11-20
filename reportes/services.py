"""ReporteService: caracterización de pacientes y estadísticas de demanda/atención por profesional y policlínico."""
import csv
import io
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone

from citas.models import Cita
from core.fechas import MESES_CORTOS

PERIODOS = [("1m", "Último mes", 1), ("3m", "Últimos 3 meses", 3), ("6m", "Últimos 6 meses", 6),
            ("12m", "Últimos 12 meses", 12)]
TRAMOS_EDAD = [("0–14", 0, 14), ("15–29", 15, 29), ("30–59", 30, 59), ("60 o más", 60, 200)]


@dataclass
class Filtros:
    desde: date
    hasta: date
    etiqueta: str
    policlinico: object = None
    profesional: object = None


def _restar_meses(d: date, meses: int) -> date:
    m = d.month - meses
    a = d.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    return date(a, m, 1)


def construir_filtros(periodo: str, policlinico=None, profesional=None, hoy: date | None = None) -> Filtros:
    hoy = hoy or timezone.localdate()
    meses = dict((k, n) for k, _, n in PERIODOS).get(periodo, 3)
    desde = _restar_meses(hoy, meses - 1)
    etiqueta = (f"{MESES_CORTOS[desde.month - 1].capitalize()}–{MESES_CORTOS[hoy.month - 1].capitalize()} {hoy.year}"
                if meses > 1 else f"{MESES_CORTOS[hoy.month - 1].capitalize()} {hoy.year}")
    return Filtros(desde, hoy, etiqueta, policlinico, profesional)


def _pct(parte, total) -> float:
    return round(100 * parte / total, 1) if total else 0.0


class ReporteService:
    def _citas(self, f: Filtros):
        qs = (Cita.objects.filter(cupo__fecha__range=(f.desde, f.hasta))
              .select_related("paciente", "asistencia", "cupo__agenda__profesional__especialidad",
                              "cupo__agenda__policlinico"))
        if f.policlinico:
            qs = qs.filter(cupo__agenda__policlinico=f.policlinico)
        if f.profesional:
            qs = qs.filter(cupo__agenda__profesional=f.profesional)
        return qs

    @staticmethod
    def _asistencia(citas):
        asistio = [c for c in citas if c.asistencia_registrada and c.asistencia_registrada.asistio]
        no_asistio = [c for c in citas if c.asistencia_registrada and not c.asistencia_registrada.asistio]
        return asistio, no_asistio

    def caracterizacion(self, f: Filtros) -> dict:
        citas = list(self._citas(f))
        asistio, no_asistio = self._asistencia(citas)
        pacientes = {c.paciente_id: c.paciente for c in asistio}.values()
        n = len(pacientes)
        menores = sum(1 for p in pacientes if p.edad < 18)
        sexo = Counter(p.sexo for p in pacientes)
        edades = Counter()
        for p in pacientes:
            for nombre, a, b in TRAMOS_EDAD:
                if a <= p.edad <= b:
                    edades[nombre] += 1
        nac = Counter(p.nacionalidad for p in pacientes).most_common()
        nacionalidades = nac[:3] + ([("Otras", sum(x for _, x in nac[3:]))] if len(nac) > 3 else [])
        # Inasistencia por mes
        por_mes = defaultdict(lambda: [0, 0])
        for c in asistio + no_asistio:
            clave = (c.cupo.fecha.year, c.cupo.fecha.month)
            por_mes[clave][0 if c.asistencia_registrada.asistio else 1] += 1
        meses = []
        d = date(f.desde.year, f.desde.month, 1)
        while d <= f.hasta:
            a, na = por_mes[(d.year, d.month)]
            meses.append({"mes": MESES_CORTOS[d.month - 1].capitalize(), "pct": round(_pct(na, a + na))})
            d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
        max_edad = max(edades.values(), default=1)
        max_nac = max((x for _, x in nacionalidades), default=1)
        return {
            "atendidos": n,
            "adultos": n - menores, "ninos": menores,
            "inasistencia": _pct(len(no_asistio), len(asistio) + len(no_asistio)),
            "mujeres": round(_pct(sexo.get("F", 0), n)), "hombres": round(_pct(sexo.get("M", 0), n)),
            "edades": [{"tramo": t, "n": edades.get(t, 0), "ancho": round(100 * edades.get(t, 0) / max_edad)}
                       for t, _, _ in TRAMOS_EDAD],
            "nacionalidades": [{"nombre": k, "n": v, "ancho": round(100 * v / max_nac)} for k, v in nacionalidades],
            "meses": meses,
            "max_mes": max((m["pct"] for m in meses), default=0) or 1,
        }

    def demanda(self, f: Filtros) -> dict:
        citas = list(self._citas(f))
        filas_prof, filas_pol = {}, {}
        for c in citas:
            prof, pol = c.cupo.agenda.profesional, c.cupo.agenda.policlinico
            for dic, clave, base in ((filas_prof, prof.pk, {"nombre": prof.nombre, "detalle": prof.especialidad.nombre,
                                                              "policlinicos": set()}),
                                     (filas_pol, pol.pk, {"nombre": pol.nombre, "detalle": ""})):
                fila = dic.setdefault(clave, {**base, "pedidas": 0, "atenciones": 0, "inasistencias": 0})
                fila["pedidas"] += 1
                a = c.asistencia_registrada
                if a and a.asistio:
                    fila["atenciones"] += 1
                elif a:
                    fila["inasistencias"] += 1
            filas_prof[prof.pk]["policlinicos"].add(pol.nombre)
        for fila in list(filas_prof.values()) + list(filas_pol.values()):
            fila["inasistencia"] = round(_pct(fila["inasistencias"], fila["atenciones"] + fila["inasistencias"]))
            if "policlinicos" in fila:
                fila["policlinicos"] = ", ".join(sorted(fila["policlinicos"]))
        asistio, no_asistio = self._asistencia(citas)
        return {
            "pedidas": len(citas),
            "atenciones": len(asistio),
            "inasistencia": _pct(len(no_asistio), len(asistio) + len(no_asistio)),
            "por_profesional": sorted(filas_prof.values(), key=lambda x: -x["pedidas"]),
            "por_policlinico": sorted(filas_pol.values(), key=lambda x: -x["pedidas"]),
        }

    def csv_demanda(self, f: Filtros) -> str:
        d = self.demanda(f)
        salida = io.StringIO()
        w = csv.writer(salida, delimiter=";")
        w.writerow(["Profesional", "Especialidad", "Policlínico(s)", "Horas pedidas", "Atenciones", "Inasistencia %"])
        for x in d["por_profesional"]:
            w.writerow([x["nombre"], x["detalle"], x["policlinicos"], x["pedidas"], x["atenciones"], x["inasistencia"]])
        w.writerow([])
        w.writerow(["Policlínico", "", "", "Horas pedidas", "Atenciones", "Inasistencia %"])
        for x in d["por_policlinico"]:
            w.writerow([x["nombre"], "", "", x["pedidas"], x["atenciones"], x["inasistencia"]])
        return "﻿" + salida.getvalue()  # BOM para que Excel lea bien los acentos


def indicadores_admin(hoy: date | None = None, dias: int = 14) -> dict:
    """Resumen de agendas para el inicio de Administración (próximos 14 días)."""
    from agenda.models import Cupo
    from lista_espera.models import SolicitudEspera
    from profesionales.models import Profesional

    hoy = hoy or timezone.localdate()
    hasta = hoy + timedelta(days=dias - 1)
    cupos = (Cupo.objects.filter(fecha__range=(hoy, hasta), agenda__activa=True, agenda__profesional__activo=True)
             .select_related("agenda__profesional__especialidad").prefetch_related("citas"))
    espera = list(SolicitudEspera.objects.filter(estado__in=SolicitudEspera.ACTIVOS)
                  .values_list("profesional_id", "especialidad_id"))
    filas = {}
    for p in Profesional.objects.filter(activo=True).select_related("especialidad"):
        filas[p.pk] = {"profesional": p, "ofrecidos": 0, "con_cita": 0, "bloqueados": 0, "disponibles": 0,
                       "espera": sum(1 for prof, esp in espera if prof == p.pk or (prof is None and esp == p.especialidad_id))}
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
    abiertos = sum(f["ofrecidos"] - f["bloqueados"] for f in filas)
    con_cita = sum(f["con_cita"] for f in filas)
    return {
        "profesionales_activos": len(filas),
        "cupos_ofrecidos": sum(f["ofrecidos"] for f in filas),
        "ocupacion": round(_pct(con_cita, abiertos)),
        "en_espera": len(espera),
        "filas": filas,
        "alertas": [f for f in filas if f["disponibles"] == 0 and f["espera"] > 0],
        "dias": dias,
    }

"""Guardias: referencia (comisión o generador) frente a guardias elegidas por el modelo con las mismas cuotas.

    python exp_guardias.py instancias/reales/*_IF.json --tl 120 --salida resultados/guardias_cuotas_reales.csv

Por cada instancia escribe dos filas: 'referencia' (guardias dadas, modelo base, óptimo) y 'cuotas' (el modelo elige los días).
Reanudable.
"""
import argparse
import csv
from pathlib import Path

from radplan import Config, Instancia, construir, evaluar, resolver
from radplan.guardias import CFG, indicadores_guardias, resolver_cuotas

BASE = Config(cobertura="blanda")
KPI = ["demanda", "servicios", "apoyos", "SG", "P", "RJ", "obligatorios_sin_cubrir", "idoneidad0", "idoneidad1", "idoneidad2", "idoneidad3"] + [f"prioridad{p}" for p in range(7)]
KG = ["cuotas_distintas", "solapes", "consecutivas", "max7", "dias_cambiados", "salientes_laborables", "titular_de_saliente", "guardias_dia_ok"]
CAMPOS = ["instancia", "version", "nF", "nS", "nD", "estado", "objetivo", "cota", "gap", "tiempo", "violaciones"] + KPI + KG

ap = argparse.ArgumentParser()
ap.add_argument("instancias", nargs="+")
ap.add_argument("--tl", type=float, default=120)
ap.add_argument("--salida", required=True)
ap.add_argument("--sin-finde", action="store_true", help="no fijar la cuota de fin de semana (solo el total)")
a = ap.parse_args()
sal = Path(a.salida)
hechos = set()
if sal.exists():
    with open(sal, newline="", encoding="utf-8") as fh:
        hechos = {(r["instancia"], r["version"]) for r in csv.DictReader(fh)}
with open(sal, "a", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, CAMPOS, extrasaction="ignore")
    if not hechos:
        w.writeheader()
    for ruta in sorted(a.instancias):
        I = Instancia.cargar(ruta)
        com = dict(instancia=I.nombre, nF=I.nF, nS=I.nS, nD=I.nD)
        if (I.nombre, "referencia") not in hechos:
            r = resolver(construir(I, BASE), tl=a.tl, hilos=2)
            ev = evaluar(I, r["sol"], BASE)
            w.writerow(dict(com, version="referencia", estado=r["estado"], objetivo=round(r["objetivo"], 3), cota=round(r["cota"], 3), gap=round(100 * r["gap"], 3),
                            tiempo=round(r["tiempo"], 1), violaciones=ev["n_violaciones"], **ev["kpi"], **indicadores_guardias(I, r["sol"])))
        if (I.nombre, "cuotas") not in hechos:
            r = resolver_cuotas(I, tl=a.tl, fijar_finde=not a.sin_finde)
            fila = dict(com, version="cuotas", estado=r["estado"], tiempo=round(r["tiempo"], 1))
            if r["sol"]:
                fila.update(objetivo=round(r["objetivo"], 3), cota=round(r["cota"], 3), gap=round(100 * r["gap"], 3),
                            violaciones=r["ev"]["n_violaciones"], **r["ev"]["kpi"], **r["kg"])
            elif r.get("motivo"):
                fila["estado"] = "infactible: " + "; ".join(r["motivo"][:2])
            w.writerow(fila)
            print(I.nombre, fila["estado"], fila.get("objetivo"), fila.get("gap"), fila["tiempo"], flush=True)
        fh.flush()

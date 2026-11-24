"""Lanzador de experimentos: instancias x configuraciones -> CSV (reanudable).

    python -m radplan.experimentos instancias/semi --config base guardias --tl 300 --salida resultados/semi.csv
"""
import argparse
import csv
import time
from dataclasses import replace
from pathlib import Path

from .comprobar import evaluar
from .instancia import Instancia
from .modelo import Config, construir, resolver

CONFIGS = {
    "excel": Config(jerarquia="excel", idoneidad0="prohibida"),            # el modelo que usa el hospital (hasta v13)
    "excel_v15": Config(jerarquia="excel"),
    "base": Config(cobertura="blanda"),                                     # el del artículo, guardias dadas
    "sin_jerarquia": Config(cobertura="blanda", jerarquia="no"),
    "guardias": Config(cobertura="blanda", guardias="modelo"),              # el modelo decide y equilibra las guardias
    "guardias_k3": Config(cobertura="blanda", guardias="modelo", max_servicios=3),
    "base_k3": Config(cobertura="blanda", max_servicios=3),
}
CAMPOS = ["instancia", "config", "nF", "nS", "nD", "variables", "restricciones", "estado", "objetivo", "cota", "gap",
          "t_construir", "t_resolver", "violaciones", "objetivo_comprobado", "demanda", "servicios", "apoyos", "SG", "P", "RJ",
          "obligatorios_sin_cubrir", "idoneidad0", "idoneidad1", "idoneidad2", "idoneidad3"] + [f"prioridad{p}" for p in range(7)]


def ejecutar(I, nombre_cfg, cfg, solver="highs", tl=None, gap=0.0, hilos=None):
    t0 = time.time()
    m = construir(I, cfg)
    fila = dict(instancia=I.nombre, config=nombre_cfg, nF=I.nF, nS=I.nS, nD=I.nD, t_construir=round(time.time() - t0, 2),
                variables=sum(1 for v in m.component_data_objects(__import__("pyomo.environ").environ.Var) if not v.fixed),
                restricciones=len(m.c))
    r = resolver(m, solver, tl, gap, hilos)
    fila.update(estado=r["estado"], t_resolver=round(r["tiempo"], 2))
    if r["sol"]:
        ev = evaluar(I, r["sol"], cfg)
        fila.update(objetivo=round(r["objetivo"], 3), cota=None if r["cota"] is None else round(r["cota"], 3),
                    gap=None if r["gap"] is None else round(100 * r["gap"], 3), violaciones=ev["n_violaciones"],
                    objetivo_comprobado=round(ev["objetivo"], 3), **{k: v for k, v in ev["kpi"].items() if k in CAMPOS})
    return fila, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("instancias", nargs="+", help="ficheros .json o carpetas")
    ap.add_argument("--config", nargs="+", default=["base"], choices=sorted(CONFIGS))
    ap.add_argument("--solver", default="highs")
    ap.add_argument("--tl", type=float, default=300)
    ap.add_argument("--gap", type=float, default=0.0)
    ap.add_argument("--hilos", type=int)
    ap.add_argument("--salida", default="resultados/resultados.csv")
    ap.add_argument("--filtro", default="")
    a = ap.parse_args()
    rutas = sorted(q for p in map(Path, a.instancias) for q in ([p] if p.is_file() else p.rglob("*.json")) if a.filtro in q.name)
    sal = Path(a.salida)
    sal.parent.mkdir(parents=True, exist_ok=True)
    hechos = set()
    if sal.exists():
        with open(sal, newline="", encoding="utf-8") as fh:
            hechos = {(r["instancia"], r["config"]) for r in csv.DictReader(fh)}
    with open(sal, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, CAMPOS, extrasaction="ignore")
        if not hechos:
            w.writeheader()
        for ruta in rutas:
            I = Instancia.cargar(ruta)
            for c in a.config:
                if (I.nombre, c) in hechos:
                    continue
                fila, _ = ejecutar(I, c, CONFIGS[c], a.solver, a.tl, a.gap, a.hilos)
                w.writerow(fila); fh.flush()
                print(f"{I.nombre:34s} {c:14s} {fila['estado']:10s} obj={fila.get('objetivo')} gap%={fila.get('gap')} "
                      f"t={fila['t_resolver']}s viol={fila.get('violaciones')}", flush=True)


if __name__ == "__main__":
    main()

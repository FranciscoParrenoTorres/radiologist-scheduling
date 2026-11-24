"""Guardias con cuotas: ganancia en función del número máximo de guardias que se permite mover respecto a las reales.

    python exp_guardias_cambios.py      # 8 meses reales (sin septiembre) -> resultados/guardias_cuotas_cambios.csv
"""
import csv
import glob
from pathlib import Path

from radplan import Instancia, evaluar, resolver
from radplan.guardias import CFG, construir_cuotas, indicadores_guardias

AQUI = Path(__file__).resolve().parent
CAMPOS = ["instancia", "max_movidas", "estado", "objetivo", "movidas", "servicios", "idoneidad0", "idoneidad1", "idoneidad2", "idoneidad3", "violaciones", "tiempo"]
with open(AQUI / "resultados/guardias_cuotas_cambios.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, CAMPOS, extrasaction="ignore")
    w.writeheader()
    for ruta in sorted(glob.glob(str(AQUI / "instancias/reales/*_IF.json"))):
        if "-09_" in ruta:
            continue
        I = Instancia.cargar(ruta)
        for mx in (0, 2, 4, 6, 8, 10, 15, 20, 30, 40, 999):
            m = construir_cuotas(I)
            ref = [(f, t) for f in range(I.nF) for t in range(I.nD) if I.guardia[f][t]]
            fuera = [k for k in ref if k not in m.y or m.y[k].fixed]      # guardias reales que el modelo no admite
            m.c.add(sum(1 - m.y[k] for k in ref if k not in fuera) <= mx - len(fuera)) if mx >= len(fuera) else None
            r = resolver(m, tl=60, hilos=2) if mx >= len(fuera) else {"estado": "infactible", "sol": None, "tiempo": 0}
            fila = dict(instancia=I.nombre, max_movidas=mx, estado=r["estado"], tiempo=round(r["tiempo"], 1))
            if r["sol"]:
                ev = evaluar(I, r["sol"], CFG)
                fila.update(objetivo=r["objetivo"], movidas=indicadores_guardias(I, r["sol"])["dias_cambiados"] // 2,
                            violaciones=ev["n_violaciones"], **ev["kpi"])
            w.writerow(fila); fh.flush()

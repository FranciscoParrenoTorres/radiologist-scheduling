"""Experimentos complementarios para el artículo (reanudable).

  - niveles de la jerarquía titular/suplentes (0..3) y objetivo con prioridad dominante ('lexico')
  - heurísticos que reproducen el procedimiento manual (orden alfabético, con y sin titulares primero)
  - indicadores adicionales: titular disponible fuera de su puesto y puestos distintos por facultativo

    python exp_articulo.py            -> resultados/articulo.csv
"""
import csv
import glob
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

from radplan import Config, Instancia, construir, evaluar, resolver

AQUI = Path(__file__).resolve().parent
SALIDA = AQUI / "resultados" / "articulo.csv"
BASE = Config(cobertura="blanda")
CONFIGS = {
    "base": BASE,
    "niveles2": replace(BASE, niveles=2),
    "niveles1": replace(BASE, niveles=1),
    "niveles0": replace(BASE, niveles=0),
    "sin_jerarquia": replace(BASE, jerarquia="no"),
    "lexico": replace(BASE, w_prio=10.0),          # 10 > máxima diferencia de idoneidad: la prioridad domina
}
# Orden alfabético de la plantilla real, como permutación de los índices de la instancia anonimizada
# (los cuatro últimos facultativos se añadieron después)
ALFA = [0, 1, 2, 3, 4, 5, 27, 6, 7, 28, 8, 29, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 30, 21, 22, 23, 24, 25, 26]
KPI = ["demanda", "servicios", "apoyos", "SG", "P", "RJ", "E", "obligatorios_sin_cubrir",
       "idoneidad0", "idoneidad1", "idoneidad2", "idoneidad3"] + [f"prioridad{p}" for p in range(7)]
CAMPOS = ["instancia", "metodo", "estado", "objetivo", "gap", "t_resolver", "violaciones"] + KPI + \
         [f"dem_prioridad{p}" for p in range(7)] + ["titular_disp", "titular_fuera", "titular_fuera_cerrado", "serv_distintos"]


def disponible(I, f, t):
    return I.laborable[t] and I.estado[f][t] == "" and not I.saliente(f, t)


def puede(I, f, s, t, cero=False):
    if not I.compatible(f, s):
        return False
    if I.guardia[f][t] and I.serv[s]["turno"] == "T":
        return False
    return I.ido[f][s] > 0 or (cero and I.serv[s]["prioridad"] == 0)


def heuristico(I, titulares_primero):
    A = [[-1] * I.nD for _ in range(I.nF)]
    orden = ALFA if I.nF == len(ALFA) else list(range(I.nF))
    for t in range(I.nD):
        if not I.laborable[t]:
            continue
        libres = {f for f in range(I.nF) if disponible(I, f, t)}
        cub = Counter()
        for f in list(libres):                                   # 1. fijos
            s = I.fijo[f][t]
            if s >= 0 and I.dem[s][t] > cub[s]:
                A[f][t] = s; cub[s] += 1; libres.discard(f)
        abiertos = [s for s in range(I.nS) if I.dem[s][t] > 0 and I.serv[s].get("en_objetivo", True)]
        if titulares_primero:                                    # 2. titulares a su puesto
            for f in orden:
                s = I.fac[f]["titular"]
                if f in libres and s is not None and s in abiertos and cub[s] < I.dem[s][t] and puede(I, f, s, t):
                    A[f][t] = s; cub[s] += 1; libres.discard(f)
        for f in orden:                                          # 3. orden alfabético, puesto más prioritario
            if f not in libres:
                continue
            cand = [s for s in abiertos if cub[s] < I.dem[s][t] and puede(I, f, s, t)]
            if cand:
                s = min(cand, key=lambda s: (I.serv[s]["prioridad"], -I.ido[f][s], s))
                A[f][t] = s; cub[s] += 1; libres.discard(f)
        for s in abiertos:                                       # 4. obligatorios sin cubrir
            while I.serv[s]["prioridad"] == 0 and cub[s] < I.dem[s][t]:
                f = next((f for f in orden if f in libres and puede(I, f, s, t, cero=True)), None)
                if f is None:
                    break
                A[f][t] = s; cub[s] += 1; libres.discard(f)
    return {"asig": A, "guardia": [list(g) for g in I.guardia]}


def extra(I, A):
    """Titular disponible fuera de su puesto (sobre puestos-día abiertos con algún titular disponible) y puestos distintos."""
    tit = defaultdict(list)
    for f in range(I.nF):
        if I.fac[f]["titular"] is not None:
            tit[I.fac[f]["titular"]].append(f)
    k = Counter()
    for t in range(I.nD):
        if not I.laborable[t]:
            continue
        for s, fs in tit.items():
            if not I.dem[s][t]:
                continue
            disp = [f for f in fs if disponible(I, f, t) and I.fijo[f][t] < 0 and puede(I, f, s, t)]
            if disp:
                k["titular_disp"] += 1
                if not any(A[f][t] == s for f in fs):
                    k["titular_fuera"] += 1
                    if not any(A[g][t] == s for g in range(I.nF)):
                        k["titular_fuera_cerrado"] += 1
    k["serv_distintos"] = sum(len({s for s in A[f] if s >= 0}) for f in range(I.nF))
    return dict(k)


def fila(I, metodo, sol, r=None):
    ev = evaluar(I, sol, BASE if metodo.startswith("H-") else CONFIGS[metodo])
    lab = [t for t in range(I.nD) if I.laborable[t]]
    dem = Counter()
    for s in range(I.nS):
        dem[I.serv[s]["prioridad"]] += sum(I.dem[s][t] for t in lab)
    out = dict(instancia=I.nombre, metodo=metodo, violaciones=ev["n_violaciones"], objetivo=round(ev["objetivo"], 3),
               **{k: ev["kpi"].get(k, 0) for k in KPI}, **{f"dem_prioridad{p}": dem[p] for p in range(7)}, **extra(I, sol["asig"]))
    if r:
        out.update(estado=r["estado"], gap=r["gap"], t_resolver=round(r["tiempo"], 2))
    return out


def main():
    rutas = sorted(glob.glob(str(AQUI / "instancias/reales/*_IF.json"))) + sorted(glob.glob(str(AQUI / "instancias/semi/*.json")))
    hechos = set()
    if SALIDA.exists():
        with open(SALIDA, newline="", encoding="utf-8") as fh:
            hechos = {(r["instancia"], r["metodo"]) for r in csv.DictReader(fh)}
    with open(SALIDA, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, CAMPOS, extrasaction="ignore")
        if not hechos:
            w.writeheader()
        for ruta in rutas:
            I = Instancia.cargar(ruta)
            for nombre, cfg in CONFIGS.items():
                if (I.nombre, nombre) in hechos:
                    continue
                r = resolver(construir(I, cfg), "highs", tl=120)
                w.writerow(fila(I, nombre, r["sol"], r)); fh.flush()
            for nombre, tp in (("H-alfabetico", False), ("H-titulares", True)):
                if (I.nombre, nombre) not in hechos:
                    w.writerow(fila(I, nombre, heuristico(I, tp))); fh.flush()
            print(I.nombre, flush=True)


if __name__ == "__main__":
    main()

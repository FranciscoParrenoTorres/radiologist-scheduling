"""Prototipo: lee los Excel de SolverStudio, reconstruye el modelo en Pyomo y lo compara con la
solución guardada en cada libro.

    pip install pyomo highspy openpyxl
    python prototipo.py                 # todos los libros de ./excel
    python prototipo.py enero           # solo los que contengan "enero"
    python prototipo.py --solver cbc    # otro solver de Pyomo (cbc, gurobi, ...)

Columnas de salida
    guardada  valor objetivo de la matriz de la hoja 'Solucion' evaluada con el modelo
    excel     óptimo con la jerarquía titular/suplentes tal como está programada en SolverStudio
    articulo  óptimo con la jerarquía tal como está escrita en el artículo (restricción c7)

Es un prototipo de comprobación, no el paquete definitivo: mantiene a propósito las rarezas del
modelo de Excel (31 columnas de día aunque el mes tenga menos, servicio 21 fuera del objetivo...).
"""
import argparse
import sys
import time
import warnings
from pathlib import Path

import openpyxl
import pyomo.environ as pyo

warnings.filterwarnings("ignore")
NF, NS, ND = 40, 35, 31            # tamaño fijo de las tablas del Excel
NIVELES = ("tit", "sup1", "sup2", "sup3")


def norm(v):
    return " ".join(str(v).upper().split()) if v is not None else ""


def leer(ruta):
    """Devuelve un diccionario con los mismos datos que SolverStudio pasa al modelo."""
    wb = openpyxl.load_workbook(ruta, data_only=True)
    F, S, I, X, SOL, E = (wb[n] for n in ("Facultativos", "Servicios", "Idoneidad", "Fijos_cod", "Solucion", "Especificaciones"))
    num = lambda v: int(v) if isinstance(v, (int, float)) else 0
    rf, rs, rd = range(1, NF + 1), range(1, NS + 1), range(1, ND + 1)
    ins = dict(nF=num(F["B1"].value), nS=num(S["B1"].value), nD=num(X["B3"].value), mes=S["O4"].value, anio=S["O5"].value)
    ins["nombre_s"] = {s: S.cell(15 + s, 2).value for s in rs}
    ins["prio"] = {s: num(S.cell(15 + s, 4).value) for s in rs}
    ins["turno_s"] = {s: S.cell(15 + s, 5).value or 0 for s in rs}
    ins["dem"] = {(s, d): num(S.cell(15 + s, 6 + d).value) for s in rs for d in rd}
    ins["turno_f"] = {f: F.cell(3 + f, 11).value or 0 for f in rf}
    ins["ido"] = {(f, s): num(I.cell(8 + f, 3 + s).value) for f in rf for s in rs}
    ins["fijos"] = {(f, d): num(X.cell(7 + f, 7 + d).value) for f in rf for d in rd}
    ins["tipo"] = {d: X.cell(6, 7 + d).value for d in rd}
    for k, col in zip(NIVELES, (4, 5, 6, 7)):
        ins[k] = {f: num(X.cell(7 + f, col).value) for f in rf}
    ins["sol"] = {(f, d): num(SOL.cell(6 + f, 4 + d).value) for f in rf for d in rd}
    ins["espec"] = {(f, d): E.cell(11 + f, 4 + d).value for f in rf for d in rd}
    return ins


def codificar(ins):
    """Recalcula 'fijos' desde el texto de Especificaciones, sin depender de las fórmulas de Fijos_cod.
    Devuelve (matriz, celdas no reconocidas)."""
    ids = {norm(n): s for s, n in ins["nombre_s"].items() if n not in (None, 0, "")}
    base = {"G": 100, "G_RJ": 150, "RJ": 200, "P": 300, "E": 300, "SG": 300}
    cod, raras = {}, []
    for (f, d), v in ins["espec"].items():
        t = norm(v)
        if not t:
            cod[f, d] = 0
        elif t in base:
            cod[f, d] = base[t]
        elif t in ids:
            cod[f, d] = ids[t]
        elif t.startswith("G_") and t[2:] in ids:
            cod[f, d] = 100 + ids[t[2:]]
        else:
            cod[f, d] = None
            raras.append((f, d, v))
    return cod, raras


def construir(ins, version="v15", jerarquia="excel"):
    """version: v13 (idoneidad 0 prohibida siempre) | v14/v15 (permitida con penalización en prioridad 0).
    jerarquia: 'excel' (como en SolverStudio) | 'articulo' (restricción c7) | 'no'."""
    nF, nS, nD = ins["nF"], ins["nS"], ins["nD"]
    fij, tipo, ido, prio, dem = ins["fijos"], ins["tipo"], ins["ido"], ins["prio"], ins["dem"]
    FF, SS, DD, R, SR = range(1, NF + 1), range(1, NS + 1), range(1, ND + 1), range(1, nF + 1), range(1, nS + 1)
    m = pyo.ConcreteModel()
    m.x = pyo.Var(FF, SS, DD, within=pyo.Binary)
    m.z = pyo.Var(SS, DD, within=pyo.Binary)

    def coef(f, s):                                  # el servicio 21 (Almansa) está fuera del objetivo
        if f > nF or s > nS or s == 21:
            return 0
        c = ido[f, s] + 7 - prio[s]
        return c - 10000 if version != "v13" and prio[s] == 0 and ido[f, s] == 0 else c

    m.coef = coef
    m.obj = pyo.Objective(expr=sum(coef(f, s) * m.x[f, s, d] for f in FF for s in SS for d in DD if coef(f, s)), sense=pyo.maximize)
    m.c = pyo.ConstraintList()
    m.avisos = []

    for s in SS:
        for d in DD:
            cubre = sum(m.x[f, s, d] for f in FF)
            m.c.add(cubre == dem[s, d] if prio[s] == 0 else cubre <= dem[s, d])
            m.c.add(sum(m.x[f, s, d] for f in R) <= dem[s, d] * m.z[s, d])
    for f in FF:
        for d in DD:
            total, c = sum(m.x[f, s, d] for s in SR), fij[f, d]
            m.c.add(total <= 1)
            if c in (100, 150):                      # guardia: sin servicios de tarde
                m.c.add(sum(m.x[f, s, d] for s in SR if ins["turno_s"][s] == "T") == 0)
            if 100 <= c < 200:                       # saliente de guardia
                if tipo[d] == "S" and d <= nD - 2:
                    m.c.add(sum(m.x[f, s, d + 2] for s in SR) == 0)
                elif tipo[d] != "S" and d <= nD - 1:
                    m.c.add(sum(m.x[f, s, d + 1] for s in SR) == 0)
            if c >= 200 or c == 150:                 # permiso, reducción, excepción
                m.c.add(total == 0)
        for s in SS:
            sin_ido = ido[f, s] == 0 and (version == "v13" or prio[s] > 0)
            sin_turno = ins["turno_s"][s] != ins["turno_f"][f] and ins["turno_f"][f] != "M/T"
            if sin_ido or sin_turno:
                for d in range(1, nD + 1):
                    m.x[f, s, d].fix(0)

    def disponible(f, d):
        if fij[f, d] not in (0, 100):
            return False
        if d > 1 and 100 <= fij[f, d - 1] < 200:
            return False
        return not (d > 2 and tipo[d - 2] == "S" and 100 <= fij[f, d - 2] < 200)

    def suyo(f, nivel, d):
        return sum(m.x[f, s, d] for s in SR if ins[nivel][f] == s)

    for s in (SS if jerarquia != "no" else ()):
        for d in DD:
            if any(fij[f, d] in (s, s + 100) for f in R):      # ya hay alguien fijado en el servicio
                continue
            cand = {k: [f for f in R if ins[k][f] == s and disponible(f, d)] for k in NIVELES}
            e = None
            if jerarquia == "articulo":
                for k, nivel in enumerate(NIVELES):
                    if cand[nivel]:
                        e = sum(m.x[f, s, d] + sum(suyo(f, NIVELES[j], d) for j in range(k)) for f in cand[nivel])
                        break
            else:
                lmx = tipo[d] in ("L", "M", "X")
                if cand["tit"]:                                # primer titular L-X, último J-V
                    e = m.x[cand["tit"][0 if lmx else -1], s, d]
                elif cand["sup1"] and lmx:                     # rama L-X: acumula suplentes y solo vale si alguno es titular de otro servicio
                    if any(ins["tit"][f] for f in cand["sup1"]):
                        e = sum(m.x[f, s, d] + suyo(f, "tit", d) for f in cand["sup1"])
                    else:
                        m.avisos.append(("suplente 1 ignorado", ins["nombre_s"][s], d))
                elif cand["sup1"]:
                    f = cand["sup1"][0]
                    e = m.x[f, s, d] + suyo(f, "tit", d)
                if e is None and cand["sup2"]:
                    f = cand["sup2"][0]
                    e = m.x[f, s, d] + suyo(f, "tit", d) + suyo(f, "sup1", d)
                elif e is None and cand["sup3"]:               # el código suma dos veces el servicio de suplente 1
                    f = cand["sup3"][0]
                    e = m.x[f, s, d] + suyo(f, "tit", d) + 2 * suyo(f, "sup1", d)
            if e is not None:
                m.c.add(e >= m.z[s, d])

    for f in FF:
        for d in DD:
            c = fij[f, d]
            if 0 < c < 100 or (100 < c < 200 and c != 150):
                g1 = d > 1 and 100 <= fij[f, d - 1] < 200 and fij[f, d - 1] != 150
                g2 = d > 2 and tipo[d - 2] == "S" and 100 <= fij[f, d - 2] < 200 and fij[f, d - 2] != 150
                if g1 or g2:
                    m.avisos.append(("fijo en saliente de guardia", f, d))
                    continue
                s = c if c < 100 else c - 100
                if dem[s, d] == 0:
                    m.avisos.append(("fijo en servicio cerrado", f, ins["nombre_s"][s], d))
                m.x[f, s, d].unfix()
                m.c.add(m.x[f, s, d] == 1)
    return m


def valor_guardada(ins, m):
    return sum(m.coef(f, s) for (f, d), s in ins["sol"].items() if s)


def resolver(m, solver):
    opt = pyo.SolverFactory(solver)
    res = opt.solve(m, load_solutions=False)
    estado = str(res.solver.termination_condition)
    if estado != "optimal":
        return estado, None
    m.solutions.load_from(res)
    return estado, round(pyo.value(m.obj))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("filtro", nargs="?", default="")
    ap.add_argument("--carpeta", default=str(Path(__file__).resolve().parent / "excel"))
    ap.add_argument("--solver", default="appsi_highs")
    a = ap.parse_args()
    print(f"{'libro':46s} {'ver':3s} {'guardada':>8s} {'excel':>7s} {'articulo':>8s}  {'s':>4s}  observaciones")
    for ruta in sorted(Path(a.carpeta).rglob("*.xlsx")):
        if a.filtro.lower() not in ruta.name.lower():
            continue
        ver = "v15" if "v15" in ruta.name else "v14" if "v14" in ruta.name else "v13"
        t0 = time.time()
        ins = leer(ruta)
        cod, raras = codificar(ins)
        dif = sum(1 for k in cod if cod[k] != ins["fijos"][k])
        m = construir(ins, ver, "excel")
        guardada = valor_guardada(ins, m)
        estado, v_excel = resolver(m, a.solver)
        _, v_art = resolver(construir(ins, ver, "articulo"), a.solver)
        obs = []
        if estado != "optimal":
            obs.append(estado)
        elif guardada != v_excel:
            obs.append("la solución guardada no corresponde a los datos")
        if dif or raras:
            obs.append(f"códigos distintos de Fijos_cod: {dif}, no reconocidos: {raras[:3]}")
        obs += [str(x) for x in m.avisos if x[0] != "suplente 1 ignorado"][:2]
        n = sum(1 for x in m.avisos if x[0] == "suplente 1 ignorado")
        if n:
            obs.append(f"suplente 1 ignorado en {n} servicio-día")
        f = lambda v: "-" if v is None else str(v)
        print(f"{ruta.name[:46]:46s} {ver:3s} {guardada:8d} {f(v_excel):>7s} {f(v_art):>8s}  {time.time() - t0:4.1f}  {'; '.join(obs)}", flush=True)
        sys.stdout.flush()

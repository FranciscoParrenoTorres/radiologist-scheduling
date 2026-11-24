"""Modelo de asignación en Pyomo, con las variantes como opciones de Config."""
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

import pyomo.environ as pyo
from pyomo.core.expr.numeric_expr import LinearExpression

from .instancia import NIVELES


@dataclass
class Config:
    jerarquia: str = "articulo"      # 'articulo' (restricción c7) | 'excel' (como en SolverStudio) | 'no'
    niveles: int = 3                 # niveles de suplentes que se tienen en cuenta (0..3)
    idoneidad0: str = "penalizada"   # 'penalizada' (solo en obligatorios, con coste M_ido0) | 'prohibida'
    cobertura: str = "dura"          # obligatorios: 'dura' (igualdad) | 'blanda' (holgura con coste M_cob)
    guardias: str = "fijas"          # 'fijas' (dato) | 'modelo' (las decide el modelo)
    max_servicios: Optional[int] = None   # máximo de servicios distintos por facultativo en el horizonte
    w_prio: float = 1.0
    w_ido: float = 1.0
    M_ido0: float = 10000.0
    M_cob: float = 100000.0
    w_eq: float = 10.0               # equilibrio de guardias totales (max - min, ponderado por dedicación)
    w_eq_finde: float = 10.0         # equilibrio de guardias en fin de semana y festivo
    w_saliente: float = 3.0          # guardia cuyo saliente cae en un día que ya no se trabajaba


def coef(I, cfg, f, s):
    """Contribución al objetivo de asignar el facultativo f al servicio s."""
    sv = I.serv[s]
    if not sv.get("en_objetivo", True):
        return 0.0
    c = cfg.w_prio * (7 - sv["prioridad"]) + cfg.w_ido * I.ido[f][s]
    return c - cfg.M_ido0 if I.ido[f][s] == 0 else c


def capacidad_guardias(I, f):
    """Peso para el equilibrio: dedicación por fracción de días en que puede hacer guardia."""
    return I.fac[f]["jornada"] * sum(1 for t in range(I.nD) if I.estado[f][t] != "P") / I.nD


def terminos_jerarquia(I, cfg, s, t):
    """Lado izquierdo de la restricción titular/suplentes del servicio s el día t (>= z_st).
    Devuelve [(coef, ('x', f, servicio, dia) | ('y', f, dia))] o None si no hay restricción."""
    if cfg.jerarquia == "no" or any(I.fijo[f][t] == s for f in range(I.nF)):
        return None
    fijas = cfg.guardias == "fijas"
    niveles = NIVELES[:1 + cfg.niveles]
    cand = {k: [] for k in NIVELES}
    for k in niveles:
        cand[k] = [f for f in range(I.nF) if I.fac[f][k] == s and I.estado[f][t] == "" and I.fijo[f][t] < 0
                   and not (fijas and I.saliente(f, t))]

    def suyo(f, k, c=1):
        l = I.fac[f][k] if k in niveles else None
        return [(c, ("x", f, l, t))] if l is not None else []

    if cfg.jerarquia == "articulo":
        for i, k in enumerate(niveles):
            if cand[k]:
                e = []
                for f in cand[k]:
                    e.append((1, ("x", f, s, t)))
                    for j in range(i):
                        e += suyo(f, niveles[j])
                    if not fijas:                       # si está de saliente la restricción queda satisfecha
                        if t >= 1 and I.dow[t - 1] != 5:
                            e.append((1, ("y", f, t - 1)))
                        if t >= 2 and I.dow[t - 2] == 5:
                            e.append((1, ("y", f, t - 2)))
                return e
        return None
    # --- 'excel': réplica literal del código de SolverStudio ---
    lmx = I.dow[t] in (0, 1, 2)
    e = None
    if cand["titular"]:                                  # primer titular de lunes a miércoles, último jueves y viernes
        e = [(1, ("x", cand["titular"][0 if lmx else -1], s, t))]
    elif cand["suplente1"] and lmx:                      # solo cuenta si algún suplente es titular de otro servicio
        if any(I.fac[f]["titular"] is not None for f in cand["suplente1"]):
            e = []
            for f in cand["suplente1"]:
                e += [(1, ("x", f, s, t))] + suyo(f, "titular")
    elif cand["suplente1"]:
        f = cand["suplente1"][0]
        e = [(1, ("x", f, s, t))] + suyo(f, "titular")
    if e is None and cand["suplente2"]:
        f = cand["suplente2"][0]
        e = [(1, ("x", f, s, t))] + suyo(f, "titular") + suyo(f, "suplente1")
    elif e is None and cand["suplente3"]:                # el código suma dos veces el servicio de suplente 1
        f = cand["suplente3"][0]
        e = [(1, ("x", f, s, t))] + suyo(f, "titular") + suyo(f, "suplente1", 2)
    return e


def fijos_activos(I, cfg):
    """Fijos que se imponen. Con guardias fijas, un fijo en saliente de guardia se ignora (como en Excel)."""
    act, ignorados = {}, []
    for f in range(I.nF):
        for t in range(I.nD):
            if I.fijo[f][t] >= 0:
                if cfg.guardias == "fijas" and I.saliente(f, t):
                    ignorados.append((f, t))
                else:
                    act[f, t] = I.fijo[f][t]
    return act, ignorados


def construir(I, cfg=None):
    cfg = cfg or Config()
    if cfg.jerarquia == "excel" and cfg.guardias != "fijas":
        raise ValueError("la jerarquía 'excel' solo está definida con guardias fijas")
    fijas = cfg.guardias == "fijas"
    m = pyo.ConcreteModel()
    m.I, m.cfg, m.imposibles = I, cfg, []
    act, m.fijos_ignorados = fijos_activos(I, cfg)

    X, por_ft, por_st = [], defaultdict(list), defaultdict(list)
    for t in range(I.nD):
        if not I.laborable[t]:
            continue
        for f in range(I.nF):
            if I.estado[f][t] != "" or (fijas and I.saliente(f, t)):
                continue
            fs = act.get((f, t))
            for s in range(I.nS):
                if I.dem[s][t] == 0 or not I.compatible(f, s) or (fs is not None and s != fs):
                    continue
                if I.ido[f][s] == 0 and not (cfg.idoneidad0 == "penalizada" and I.serv[s]["prioridad"] == 0):
                    continue
                if fijas and I.guardia[f][t] and fs is None and I.serv[s]["turno"] == "T":
                    continue
                X.append((f, s, t)); por_ft[f, t].append(s); por_st[s, t].append(f)
    m.x = pyo.Var(X, within=pyo.Binary)
    enX = set(X)
    for (f, t), s in act.items():
        if (f, s, t) in enX:
            m.x[f, s, t].fix(1)
        else:
            m.imposibles.append(f"fijo imposible: facultativo {I.fac[f]['id']} en {I.serv[s]['nombre']} el día {t + 1}")

    m.c = pyo.ConstraintList()
    obj_v, obj_c = [], []
    for k in X:
        c = coef(I, cfg, k[0], k[1])
        if c:
            obj_v.append(m.x[k]); obj_c.append(c)

    # cobertura
    U = [(s, t) for s in range(I.nS) for t in range(I.nD) if I.dem[s][t] and I.serv[s]["prioridad"] == 0] if cfg.cobertura == "blanda" else []
    m.u = pyo.Var(U, within=pyo.NonNegativeReals)
    for s in range(I.nS):
        for t in range(I.nD):
            if not I.dem[s][t]:
                continue
            xs = [m.x[f, s, t] for f in por_st[s, t]]
            if I.serv[s]["prioridad"] == 0:
                if cfg.cobertura == "blanda":
                    m.c.add(sum(xs) + m.u[s, t] == I.dem[s][t])
                    obj_v.append(m.u[s, t]); obj_c.append(-cfg.M_cob)
                elif len(xs) < I.dem[s][t]:
                    m.imposibles.append(f"obligatorio sin candidatos: {I.serv[s]['nombre']} el día {t + 1}")
                else:
                    m.c.add(sum(xs) == I.dem[s][t])
            elif len(xs) > I.dem[s][t]:
                m.c.add(sum(xs) <= I.dem[s][t])
    for (f, t), ss in por_ft.items():
        if len(ss) > 1:
            m.c.add(sum(m.x[f, s, t] for s in ss) <= 1)

    # guardias decididas por el modelo
    Y = [(f, t) for f in range(I.nF) if I.fac[f]["guardias"] for t in range(I.nD) if I.estado[f][t] != "P"] if not fijas else []
    m.y = pyo.Var(Y, within=pyo.Binary)
    if not fijas:
        enY, por_t = set(Y), defaultdict(list)
        for f, t in Y:
            por_t[t].append(f)
            tarde = [m.x[f, s, t] for s in por_ft.get((f, t), ()) if I.serv[s]["turno"] == "T"]
            if tarde:
                m.c.add(m.y[f, t] + sum(tarde) <= 1)
            d = I.destino_saliente(t)
            if d < I.nD:
                if por_ft.get((f, d)):
                    m.c.add(m.y[f, t] + sum(m.x[f, s, d] for s in por_ft[f, d]) <= 1)
                elif I.laborable[d] and I.estado[f][d] != "" and cfg.w_saliente:
                    obj_v.append(m.y[f, t]); obj_c.append(-cfg.w_saliente)
            if (f, t + 1) in enY:
                m.c.add(m.y[f, t] + m.y[f, t + 1] <= 1)
            if I.dow[t] == 5 and (f, t + 2) in enY:
                m.c.add(m.y[f, t] + m.y[f, t + 2] <= 1)
        for t in range(I.nD):
            if len(por_t[t]) < I.guardias_dia[t]:
                m.imposibles.append(f"faltan facultativos para las guardias del día {t + 1}")
            elif por_t[t]:
                m.c.add(sum(m.y[f, t] for f in por_t[t]) == I.guardias_dia[t])
        m.h = pyo.Var(range(4), within=pyo.NonNegativeReals)      # hmax, hmin, wmax, wmin
        finde = [t for t in range(I.nD) if I.dow[t] >= 5 or I.dias[t]["festivo"]]
        for f in range(I.nF):
            cap = capacidad_guardias(I, f) if I.fac[f]["guardias"] else 0
            if cap > 0:
                tot = sum(m.y[f, t] for t in range(I.nD) if (f, t) in enY)
                m.c.add(tot <= cap * m.h[0]); m.c.add(tot >= cap * m.h[1])
                fin = [m.y[f, t] for t in finde if (f, t) in enY]
                if fin:
                    m.c.add(sum(fin) <= cap * m.h[2]); m.c.add(sum(fin) >= cap * m.h[3])
        obj_v += [m.h[0], m.h[1], m.h[2], m.h[3]]
        obj_c += [-cfg.w_eq, cfg.w_eq, -cfg.w_eq_finde, cfg.w_eq_finde]

    # jerarquía titular / suplentes
    Z, jer = [], {}
    if cfg.jerarquia != "no":
        for (s, t), fs in por_st.items():
            e = terminos_jerarquia(I, cfg, s, t)
            if e is not None:
                jer[s, t] = e; Z.append((s, t))
    m.z = pyo.Var(Z, within=pyo.Binary)
    for (s, t), e in jer.items():
        lhs = [c * (m.x[k[1:]] if k[0] == "x" else m.y[k[1:]]) for c, k in e
               if (k[0] == "x" and k[1:] in enX) or (k[0] == "y" and not fijas and k[1:] in enY)]
        m.c.add(sum(m.x[f, s, t] for f in por_st[s, t]) <= I.dem[s][t] * m.z[s, t])
        m.c.add(sum(lhs) >= m.z[s, t]) if lhs else m.z[s, t].fix(0)

    # máximo de servicios distintos por facultativo
    if cfg.max_servicios is not None:
        pares = sorted({(f, s) for f, s, t in X})
        m.w = pyo.Var(pares, within=pyo.Binary)
        for f, s, t in X:
            m.c.add(m.x[f, s, t] <= m.w[f, s])
        por_f = defaultdict(list)
        for f, s in pares:
            por_f[f].append(s)
        for f, ss in por_f.items():
            m.c.add(sum(m.w[f, s] for s in ss) <= cfg.max_servicios)

    m.obj = pyo.Objective(expr=LinearExpression(constant=0, linear_coefs=obj_c, linear_vars=obj_v), sense=pyo.maximize)
    return m


def extraer(m):
    I = m.I
    asig = [[-1] * I.nD for _ in range(I.nF)]
    for (f, s, t), v in m.x.items():
        if v.value is not None and v.value > 0.5:
            asig[f][t] = s
    if m.cfg.guardias == "fijas":
        g = [list(r) for r in I.guardia]
    else:
        g = [[0] * I.nD for _ in range(I.nF)]
        for (f, t), v in m.y.items():
            if v.value is not None and v.value > 0.5:
                g[f][t] = 1
    return {"asig": asig, "guardia": g}


def resolver(m, solver="highs", tl=None, gap=0.0, hilos=None):
    """Devuelve dict(estado, objetivo, cota, gap, tiempo, sol). Con 'highs' usa la interfaz directa;
    cualquier otro nombre se pasa a SolverFactory (cbc, gurobi, cplex...)."""
    r = dict(estado=None, objetivo=None, cota=None, gap=None, tiempo=0.0, sol=None, nvar=None, nres=None)
    if m.imposibles:
        r["estado"] = "infactible"; r["motivo"] = m.imposibles
        return r
    t0 = time.time()
    if solver == "highs":
        from pyomo.contrib.appsi.solvers import Highs
        opt = Highs()
        opt.config.load_solution = False
        opt.config.mip_gap = gap
        if tl:
            opt.config.time_limit = tl
        if hilos:
            opt.highs_options = {"threads": hilos}
        res = opt.solve(m)
        tc = str(res.termination_condition).split(".")[-1]
        r["estado"] = {"optimal": "optimo", "infeasible": "infactible", "maxTimeLimit": "limite"}.get(tc, tc)
        r["objetivo"], r["cota"] = res.best_feasible_objective, res.best_objective_bound
        if r["objetivo"] is not None:
            res.solution_loader.load_vars()
    else:
        opt = pyo.SolverFactory(solver)
        claves = {"gurobi": ("TimeLimit", "MIPGap", "Threads"), "cbc": ("seconds", "ratioGap", "threads"),
                  "cplex": ("timelimit", "mipgap", "threads")}.get(solver.split("_")[0], (None, None, None))
        for k, v in zip(claves, (tl, gap, hilos)):
            if k and v is not None:
                opt.options[k] = v
        res = opt.solve(m, load_solutions=False)
        tc = str(res.solver.termination_condition)
        r["estado"] = {"optimal": "optimo", "infeasible": "infactible", "maxTimeLimit": "limite"}.get(tc, "limite")
        if len(res.solution) > 0:
            m.solutions.load_from(res)
            entera = all(v.value is not None and abs(v.value - round(v.value)) < 1e-6
                         for v in m.component_data_objects(pyo.Var) if v.is_binary() and not v.fixed)
            if entera:
                r["objetivo"] = pyo.value(m.obj)
                cotas = [c for c in (res.problem.upper_bound, res.problem.lower_bound) if c is not None and abs(c) < 1e30]
                cotas += [-c for c in cotas]             # CBC devuelve la cota con el signo del problema de minimizar
                validas = [c for c in cotas if c > r["objetivo"] + 1e-6]   # si coincide con el objetivo no es una cota
                r["cota"] = r["objetivo"] if r["estado"] == "optimo" else (min(validas) if validas else None)
            else:
                r["estado"] = "sin_solucion"             # CBC se ha parado con una solución no entera
    r["tiempo"] = time.time() - t0
    if r["objetivo"] is not None:
        r["sol"] = extraer(m)
        if r["cota"] is not None:
            r["gap"] = abs(r["cota"] - r["objetivo"]) / max(1e-9, abs(r["objetivo"]))
    return r

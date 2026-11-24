"""Formación: qué mejoras de idoneidad abrirían más servicios.

Una mejora sube a `nivel` (2 por defecto) la idoneidad de un par (facultativo, servicio) que hoy vale 0 o 1.
El modelo elige como mucho k mejoras, comunes a todas las instancias que se le pasan (varios meses de la misma
plantilla), para maximizar la suma de sus objetivos. Los meses solo quedan ligados por las variables u[f, s].

    mejoras, info = elegir(instancias, k)          # modelo conjunto
    I2 = aplicar(I, mejoras)                       # instancia con la idoneidad mejorada
    ... y I2 se resuelve y se comprueba con el modelo normal (construir / resolver / evaluar)
"""
import copy
import time

import pyomo.environ as pyo

from .instancia import Instancia
from .modelo import Config, coef, construir, extraer


def candidatos(I, desde=(0, 1), nivel=2):
    """Pares (f, s) que se pueden mejorar: turno compatible, idoneidad actual en `desde` y servicio en el objetivo."""
    return [(f, s) for f in range(I.nF) for s in range(I.nS)
            if I.ido[f][s] in desde and I.ido[f][s] < nivel and I.compatible(f, s) and I.serv[s].get("en_objetivo", True)]


def aplicar(I, mejoras, nivel=2, nombre=None):
    d = {k: (copy.deepcopy(v) if k == "idoneidad" else v) for k, v in I.d.items()}
    for f, s in mejoras:
        d["idoneidad"][f][s] = max(d["idoneidad"][f][s], nivel)
    d["nombre"] = nombre or I.nombre
    return Instancia(d)


def misma_plantilla(Is):
    a = Is[0]
    return all(I.fac == a.fac and I.serv == a.serv and I.ido == a.ido for I in Is)


def construir_formacion(Is, k, cfg=None, desde=(0, 1), nivel=2, coste=None):
    """Modelo conjunto. coste = {idoneidad_actual: unidades}; por defecto cada mejora cuesta 1 y k es el número de mejoras."""
    cfg = cfg or Config(cobertura="blanda")
    if not misma_plantilla(Is):
        raise ValueError("las instancias no comparten facultativos, servicios e idoneidad")
    base = Is[0]
    pares = candidatos(base, desde, nivel)
    coste = coste or {}
    M = pyo.ConcreteModel()
    M.pares, M.sub = pares, []
    M.u = pyo.Var(pares, within=pyo.Binary)
    M.presupuesto = pyo.Constraint(expr=sum(coste.get(base.ido[f][s], 1) * M.u[f, s] for f, s in pares) <= k)
    es_par = set(pares)
    obj = 0
    for i, I in enumerate(Is):
        m = construir(aplicar(I, pares, nivel), cfg)            # todas las mejoras disponibles...
        if m.imposibles:
            raise ValueError(f"{I.nombre}: {m.imposibles[:3]}")
        m.obj.deactivate()
        P, delta = [], {}
        m.liga = pyo.ConstraintList()
        for (f, s, t), v in m.x.items():
            if (f, s) not in es_par:
                continue
            permitido = I.ido[f][s] > 0 or (cfg.idoneidad0 == "penalizada" and I.serv[s]["prioridad"] == 0)
            if v.fixed and not permitido:                        # fijo que hoy sería imposible: se deja como está
                continue
            if permitido:                                        # ...pero sin u se paga la diferencia de objetivo
                P.append((f, s, t)); delta[f, s] = coef(m.I, cfg, f, s) - coef(I, cfg, f, s)
            else:                                                # ...o directamente no se puede asignar
                m.liga.add(v <= M.u[f, s])
        m.p = pyo.Var(P, within=pyo.NonNegativeReals)
        for f, s, t in P:
            m.liga.add(m.p[f, s, t] >= m.x[f, s, t] - M.u[f, s])
        obj += m.obj.expr - sum(delta[f, s] * m.p[f, s, t] for f, s, t in P)
        M.add_component(f"mes{i}", m)
        M.sub.append(m)
    M.obj = pyo.Objective(expr=obj, sense=pyo.maximize)
    return M


def elegir(Is, k, cfg=None, desde=(0, 1), nivel=2, coste=None, tl=120, gap=0.0, hilos=None, obligadas=()):
    """Devuelve (mejoras, info). `obligadas` fija a 1 las mejoras ya decididas (para listas anidadas)."""
    from pyomo.contrib.appsi.solvers import Highs
    t0 = time.time()
    M = construir_formacion(Is, k, cfg, desde, nivel, coste)
    for par in obligadas:
        M.u[par].fix(1)
    tc = time.time() - t0
    opt = Highs()
    opt.config.load_solution = False
    opt.config.mip_gap = gap
    opt.config.time_limit = tl
    if hilos:
        opt.highs_options = {"threads": hilos}
    t0 = time.time()
    res = opt.solve(M)
    info = dict(k=k, candidatos=len(M.pares), estado=str(res.termination_condition).split(".")[-1],
                objetivo=res.best_feasible_objective, cota=res.best_objective_bound,
                t_construir=round(tc, 2), t_resolver=round(time.time() - t0, 2),
                variables=sum(1 for v in M.component_data_objects(pyo.Var) if not v.fixed),
                restricciones=sum(1 for c in M.component_data_objects(pyo.Constraint, active=True)))
    if info["objetivo"] is None:
        return None, info
    res.solution_loader.load_vars()
    info["gap"] = abs(info["cota"] - info["objetivo"]) / max(1e-9, abs(info["objetivo"]))
    info["soluciones"] = [extraer(m) for m in M.sub]
    return sorted(par for par in M.pares if M.u[par].value > 0.5), info


def describir(I, mejoras):
    return "; ".join(f"{I.fac[f]['id']}→{I.serv[s]['nombre']} ({I.ido[f][s]}→2)" for f, s in mejoras)

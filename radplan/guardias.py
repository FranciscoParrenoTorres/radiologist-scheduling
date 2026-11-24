"""Guardias con las mismas cuotas que la planificación de referencia.

El modelo elige solo los DÍAS de guardia. Cada facultativo hace exactamente las mismas guardias, totales y de fin de
semana o festivo, que en las guardias de referencia (las reales de la comisión, o las del generador), de modo que el
reparto no cambia y no hacen falta pesos de equidad. Reglas añadidas, todas observadas en los nueve meses reales:

  - cada facultativo tiene como mucho tantos salientes en día de permiso o reducción como en la referencia
    (0 en los datos reales, así que ahí quedan prohibidos);
  - como mucho `max7` guardias en 7 días seguidos (el máximo real es 3);
  - sin guardias en días consecutivos ni sábado + lunes (ya está en modelo.py).

No modifica modelo.py: añade restricciones al modelo que devuelve construir().
"""
from collections import Counter

from .comprobar import evaluar
from .modelo import Config, construir, resolver

CFG = Config(cobertura="blanda", guardias="modelo", w_eq=0.0, w_eq_finde=0.0, w_saliente=0.0)


def finde(I):
    return [t for t in range(I.nD) if I.dow[t] >= 5 or I.dias[t]["festivo"]]


def cuotas(I, guardia=None):
    """(totales, de fin de semana o festivo) por facultativo en las guardias de referencia."""
    g = guardia or I.guardia
    F = finde(I)
    return [sum(g[f]) for f in range(I.nF)], [sum(g[f][t] for t in F) for f in range(I.nF)]


def solapa(I, f, t):
    """La guardia de f el día t tendría el saliente en un día laborable en el que ya no trabaja."""
    d = I.destino_saliente(t)
    return d < I.nD and I.laborable[d] and I.estado[f][d] != ""


def construir_cuotas(I, cfg=CFG, max7=3, fijar_finde=True, sin_solape=True):
    m = construir(I, cfg)
    tot, fin = cuotas(I)
    F = set(finde(I))
    por_f = {}
    for f, t in m.y:
        por_f.setdefault(f, []).append(t)
    if sin_solape:                                       # no más solapes que en la referencia (0 en los meses reales)
        for f, ts in por_f.items():
            sol = [t for t in ts if solapa(I, f, t)]
            ref = sum(1 for t in range(I.nD) if I.guardia[f][t] and solapa(I, f, t))
            if ref == 0:
                for t in sol:
                    m.y[f, t].fix(0)
            elif len(sol) > ref:
                m.c.add(sum(m.y[f, t] for t in sol) <= ref)
    for f in range(I.nF):
        ts = sorted(por_f.get(f, []))
        libres = [t for t in ts if not m.y[f, t].fixed]
        if tot[f] > len(libres):
            m.imposibles.append(f"{I.fac[f]['id']}: {tot[f]} guardias y solo {len(libres)} días posibles")
            continue
        if not ts:
            continue
        m.c.add(sum(m.y[f, t] for t in ts) == tot[f])
        if fijar_finde:
            m.c.add(sum(m.y[f, t] for t in ts if t in F) == fin[f])
        if max7:
            for a in range(I.nD - 6):
                v = [m.y[f, t] for t in ts if a <= t < a + 7]
                if len(v) > max7:
                    m.c.add(sum(v) <= max7)
    return m


def indicadores_guardias(I, sol):
    """Indicadores propios de las guardias, para comparar las de referencia con las del modelo."""
    G, A = sol["guardia"], sol["asig"]
    k = Counter()
    tot, fin = cuotas(I, G)
    ref_t, ref_f = cuotas(I)
    k["cuotas_distintas"] = sum(tot[f] != ref_t[f] or fin[f] != ref_f[f] for f in range(I.nF))
    for f in range(I.nF):
        ds = [t for t in range(I.nD) if G[f][t]]
        k["solapes"] += sum(solapa(I, f, t) for t in ds)
        k["consecutivas"] += sum(1 for a, b in zip(ds, ds[1:]) if b - a == 1)
        k["max7"] = max(k["max7"], max((sum(G[f][a:a + 7]) for a in range(I.nD)), default=0))
        k["dias_cambiados"] += sum(G[f][t] != I.guardia[f][t] for t in range(I.nD)) // 1
        s = I.fac[f]["titular"]
        for t in range(I.nD):
            if I.laborable[t] and I.estado[f][t] == "" and I.saliente(f, t, G):
                k["salientes_laborables"] += 1
                if s is not None and I.dem[s][t]:
                    k["titular_de_saliente"] += 1          # su puesto abre y él descansa
    k["guardias_dia_ok"] = int(all(sum(G[f][t] for f in range(I.nF)) == I.guardias_dia[t] for t in range(I.nD)))
    for c in ("solapes", "consecutivas", "salientes_laborables", "titular_de_saliente"):
        k.setdefault(c, 0)
    return dict(k)


def resolver_cuotas(I, tl=120, hilos=2, **kw):
    m = construir_cuotas(I, **kw)
    r = resolver(m, "highs", tl=tl, hilos=hilos)
    if r["sol"]:
        r["ev"] = evaluar(I, r["sol"], CFG)
        r["kg"] = indicadores_guardias(I, r["sol"])
    return r

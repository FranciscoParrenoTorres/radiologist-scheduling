"""Comprobador independiente del solver: restricciones, valor objetivo e indicadores de una solución."""
from collections import Counter

from .instancia import NIVELES
from .modelo import Config, capacidad_guardias, coef, fijos_activos, terminos_jerarquia


def evaluar(I, sol, cfg=None, max_viol=50):
    """sol = {'asig': [fac][dia] -> servicio o -1, 'guardia': [fac][dia] -> 0/1}.
    Devuelve dict(violaciones, objetivo, kpi)."""
    cfg = cfg or Config()
    A, G = sol["asig"], sol.get("guardia") or I.guardia
    fijas = cfg.guardias == "fijas"
    v, obj = [], 0.0
    cub = Counter()
    for f in range(I.nF):
        for t in range(I.nD):
            s = A[f][t]
            if s < 0:
                continue
            cub[s, t] += 1
            obj += coef(I, cfg, f, s)
            n = f"{I.fac[f]['id']} en {I.serv[s]['nombre']} el día {t + 1}"
            if not I.dem[s][t]:
                v.append("servicio cerrado: " + n)
            if I.estado[f][t] != "":
                v.append(f"no disponible ({I.estado[f][t]}): " + n)
            if not I.compatible(f, s):
                v.append("turno incompatible: " + n)
            if I.ido[f][s] == 0 and not (cfg.idoneidad0 == "penalizada" and I.serv[s]["prioridad"] == 0):
                v.append("sin idoneidad: " + n)
            if I.saliente(f, t, G):
                v.append("saliente de guardia: " + n)
            if G[f][t] and I.serv[s]["turno"] == "T" and not (fijas and I.fijo[f][t] >= 0):
                v.append("tarde con guardia: " + n)
    desc = 0
    for s in range(I.nS):
        for t in range(I.nD):
            if cub[s, t] > I.dem[s][t]:
                v.append(f"demanda superada: {I.serv[s]['nombre']} el día {t + 1}")
            if I.serv[s]["prioridad"] == 0 and cub[s, t] < I.dem[s][t]:
                desc += I.dem[s][t] - cub[s, t]
                if cfg.cobertura == "dura":
                    v.append(f"obligatorio sin cubrir: {I.serv[s]['nombre']} el día {t + 1}")
    obj -= cfg.M_cob * desc
    for (f, t), s in fijos_activos(I, cfg)[0].items():
        if A[f][t] != s:
            v.append(f"fijo no respetado: {I.fac[f]['id']} en {I.serv[s]['nombre']} el día {t + 1}")
    if cfg.jerarquia != "no":
        for s in range(I.nS):
            for t in range(I.nD):
                if cub[s, t]:
                    e = terminos_jerarquia(I, cfg, s, t)
                    if e is not None and sum(c * ((A[k[1]][k[3]] == k[2]) if k[0] == "x" else G[k[1]][k[2]]) for c, k in e) < 1:
                        v.append(f"jerarquía titular/suplentes: {I.serv[s]['nombre']} el día {t + 1}")
    if cfg.max_servicios is not None:
        for f in range(I.nF):
            if len({s for s in A[f] if s >= 0}) > cfg.max_servicios:
                v.append(f"demasiados servicios distintos: {I.fac[f]['id']}")
    if not fijas:
        finde = [t for t in range(I.nD) if I.dow[t] >= 5 or I.dias[t]["festivo"]]
        rt, rf = [], []
        for t in range(I.nD):
            if sum(G[f][t] for f in range(I.nF)) != I.guardias_dia[t]:
                v.append(f"número de guardias incorrecto el día {t + 1}")
        for f in range(I.nF):
            for t in range(I.nD):
                if not G[f][t]:
                    continue
                if not I.fac[f]["guardias"] or I.estado[f][t] == "P":
                    v.append(f"guardia no permitida: {I.fac[f]['id']} el día {t + 1}")
                if (t + 1 < I.nD and G[f][t + 1]) or (I.dow[t] == 5 and t + 2 < I.nD and G[f][t + 2]):
                    v.append(f"guardias demasiado seguidas: {I.fac[f]['id']} el día {t + 1}")
                d = I.destino_saliente(t)
                if d < I.nD and I.laborable[d] and I.estado[f][d] != "":
                    obj -= cfg.w_saliente
            cap = capacidad_guardias(I, f) if I.fac[f]["guardias"] else 0
            if cap > 0:
                rt.append(sum(G[f]) / cap)
                if any(I.estado[f][t] != "P" for t in finde):
                    rf.append(sum(G[f][t] for t in finde) / cap)
        if rt:
            obj -= cfg.w_eq * (max(rt) - min(rt))
        if rf:
            obj -= cfg.w_eq_finde * (max(rf) - min(rf))
    return {"violaciones": v[:max_viol], "n_violaciones": len(v), "objetivo": obj, "kpi": indicadores(I, sol, desc)}


def indicadores(I, sol, descubiertos=0):
    """Los indicadores de resultados.txt: reparto de los facultativo-día laborables y servicios por idoneidad y prioridad."""
    A, G = sol["asig"], sol.get("guardia") or I.guardia
    lab = [t for t in range(I.nD) if I.laborable[t]]
    k = Counter(totales=I.nF * len(lab), obligatorios_sin_cubrir=descubiertos)
    for f in range(I.nF):
        for t in lab:
            s = A[f][t]
            if s >= 0:
                k["servicios"] += 1
                k[f"idoneidad{I.ido[f][s]}"] += 1
                k[f"prioridad{I.serv[s]['prioridad']}"] += 1
            elif I.estado[f][t] in ("P", "RJ", "E"):
                k[I.estado[f][t]] += 1
            elif I.estado[f][t] == "SG" or I.saliente(f, t, G):
                k["SG"] += 1
            else:
                k["apoyos"] += 1
    k["demanda"] = sum(I.dem[s][t] for s in range(I.nS) for t in lab)
    for c in ("servicios", "apoyos", "SG", "P", "RJ", "E", "idoneidad0", "idoneidad1", "idoneidad2", "idoneidad3"):
        k.setdefault(c, 0)
    return dict(k)

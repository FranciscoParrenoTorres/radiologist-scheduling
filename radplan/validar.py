"""Comprobaciones previas de una instancia: lo que en Excel aparecía como modelo infactible o aviso perdido."""
from collections import Counter


def validar(I, idoneidad0="penalizada"):
    """Devuelve (errores, avisos). Un error hace infactible el modelo con guardias fijas."""
    err, av = [], []
    fijos = Counter()
    for f in range(I.nF):
        n = I.fac[f]["id"]
        for t in range(I.nD):
            if I.guardia[f][t] and I.estado[f][t] == "P":
                av.append(f"{n} día {t + 1}: guardia en día de permiso")
            if I.guardia[f][t] and not I.fac[f]["guardias"]:
                av.append(f"{n} día {t + 1}: guardia de un facultativo que no hace guardias")
            s = I.fijo[f][t]
            if s < 0:
                continue
            ns = I.serv[s]["nombre"]
            if I.saliente(f, t):
                av.append(f"{n} día {t + 1}: fijo en {ns} estando saliente de guardia (se ignora)")
                continue
            fijos[s, t] += 1
            if not I.dem[s][t]:
                err.append(f"{n} día {t + 1}: fijo en {ns}, que está cerrado")
            if I.estado[f][t]:
                err.append(f"{n} día {t + 1}: fijo en {ns} con estado {I.estado[f][t]}")
            if not I.compatible(f, s):
                err.append(f"{n} día {t + 1}: fijo en {ns} con turno incompatible")
            if I.ido[f][s] == 0 and not (idoneidad0 == "penalizada" and I.serv[s]["prioridad"] == 0):
                err.append(f"{n} día {t + 1}: fijo en {ns} sin idoneidad")
    for (s, t), c in fijos.items():
        if I.dem[s][t] and c > I.dem[s][t]:
            err.append(f"día {t + 1}: {c} facultativos fijados en {I.serv[s]['nombre']} (demanda {I.dem[s][t]})")
    for s in range(I.nS):
        if I.serv[s]["prioridad"] == 0:
            for t in range(I.nD):
                if I.dem[s][t] and not any(I.estado[f][t] == "" and not I.saliente(f, t) and I.compatible(f, s)
                                           and (I.ido[f][s] > 0 or idoneidad0 == "penalizada") for f in range(I.nF)):
                    err.append(f"día {t + 1}: nadie puede cubrir el obligatorio {I.serv[s]['nombre']}")
    return err, av


def reparar(I):
    """Quita los fijos en servicios cerrados. Devuelve la lista de cambios."""
    cambios = []
    for f in range(I.nF):
        for t in range(I.nD):
            s = I.fijo[f][t]
            if s >= 0 and not I.dem[s][t]:
                I.fijo[f][t] = -1
                cambios.append(f"{I.fac[f]['id']} día {t + 1}: quitado el fijo en {I.serv[s]['nombre']} (cerrado)")
    return cambios

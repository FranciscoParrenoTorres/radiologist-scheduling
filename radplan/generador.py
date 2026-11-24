"""Generación de instancias.

  semisintetica(...)  la plantilla real (facultativos, servicios, idoneidad, titulares) con un calendario nuevo
  sintetica(...)      departamento inventado de cualquier tamaño, con la misma estructura que el real

Todo depende solo de la semilla, así que cada instancia se puede regenerar.
"""
import copy
import random
from collections import Counter, defaultdict
from datetime import date, timedelta

from .instancia import NIVELES, Instancia

PRESION = {"baja": 0.04, "media": 0.10, "alta": 0.30, "extrema": 0.55}   # fracción de facultativo-día laborables de permiso
FESTIVOS_FIJOS = [(1, 1), (1, 6), (5, 1), (5, 31), (6, 24), (8, 15), (9, 8), (10, 12), (11, 1), (12, 6), (12, 8), (12, 25)]


def pascua(anio):
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l) // 433
    mes = (h + l - 7 * m + 90) // 25
    return date(anio, mes, (h + l - 7 * m + 33 * mes + 19) % 32)


def festivos(anio):
    p = pascua(anio)
    return {date(anio, m, d) for m, d in FESTIVOS_FIJOS} | {p - timedelta(days=3), p - timedelta(days=2)}


def _dias(inicio, n, fest):
    return [{"fecha": (inicio + timedelta(days=i)).isoformat(), "dow": (inicio + timedelta(days=i)).weekday(),
             "festivo": (inicio + timedelta(days=i)) in fest} for i in range(n)]


def inferir_patrones(bases, min_meses=3):
    """Costumbres de fijos de las instancias reales, medidas en los meses en que aparecen (mediana):
    ('dia', f, s, dow) si casi siempre va ese día de la semana; ('semana', f, s, n) si va n veces por semana sin día fijo."""
    from statistics import median
    frec, sem = defaultdict(list), defaultdict(list)
    for I in bases:
        veces, dias_sem = Counter(), Counter(I.dow[t] for t in range(I.nD) if I.laborable[t])
        for t in range(I.nD):
            for f in range(I.nF):
                if I.laborable[t] and I.fijo[f][t] >= 0:
                    veces[f, I.fijo[f][t], I.dow[t]] += 1
        tot = Counter()
        for (f, s, w), c in veces.items():
            frec[f, s, w].append(c / dias_sem[w]); tot[f, s] += c
        for k, c in tot.items():
            sem[k].append(c / (sum(I.laborable) / 5))
    pat, con_dia = [], set()
    for (f, s, w), v in frec.items():
        if len(v) >= min_meses and median(v) >= 0.6:
            pat.append(("dia", f, s, w)); con_dia.add((f, s))
    for (f, s), v in sem.items():
        if (f, s) not in con_dia and len(v) >= min_meses and round(median(v)) >= 1:
            pat.append(("semana", f, s, round(median(v))))
    return sorted(pat)


def _calendario(d, rng, presion, guardias_dia, patrones=()):
    """Rellena estado, guardia, fijo y guardias_dia de la instancia (dict) d."""
    fac, dias, dem = d["facultativos"], d["dias"], d["demanda"]
    nF, nD, nS = len(fac), len(dias), len(d["servicios"])
    lab = [t for t in range(nD) if any(dem[s][t] for s in range(nS))]
    dow = [x["dow"] for x in dias]
    estado = [[""] * nD for _ in range(nF)]
    for f in range(nF):                                  # reducción de jornada: días fijos de la semana
        k = min(4, round((1 - fac[f]["jornada"]) * 5))
        libres = set(rng.sample(range(5), k))
        for t in lab:
            if dow[t] in libres:
                estado[f][t] = "RJ"
    objetivo, hechos, intentos = presion * nF * len(lab), 0, 0     # permisos, por bloques
    while hechos < objetivo and intentos < 50 * nF and lab:
        intentos += 1
        f, i = rng.randrange(nF), rng.randrange(len(lab))
        for t in lab[i:i + rng.choices((1, 2, 3, 5, 10), (4, 2, 1, 3, 1.5))[0]]:
            if estado[f][t] != "P":
                estado[f][t] = "P"; hechos += 1
    guardia = [[0] * nD for _ in range(nF)]              # rueda de guardias equilibrada por dedicación
    n, cuenta, finde = [], [0.0] * nF, [0.0] * nF
    G = [f for f in range(nF) if fac[f]["guardias"]]
    for t in range(nD):
        def libre(f, estricto):
            if estado[f][t] == "P" or (t >= 1 and guardia[f][t - 1]) or (t >= 2 and dow[t - 2] == 5 and guardia[f][t - 2]):
                return False
            return not estricto or (estado[f][t] == "" and (t + 1 >= nD or estado[f][t + 1] == ""))
        cand = [f for f in G if libre(f, True)]
        if len(cand) < guardias_dia:
            cand += [f for f in G if f not in cand and libre(f, False)]
        es_finde = dow[t] >= 5 or dias[t]["festivo"]
        cand.sort(key=lambda f: ((finde[f] if es_finde else cuenta[f]) / fac[f]["jornada"] + rng.random()))
        for f in cand[:guardias_dia]:
            guardia[f][t] = 1; cuenta[f] += 1; finde[f] += es_finde
        n.append(min(guardias_dia, len(cand)))
    fijo = [[-1] * nD for _ in range(nF)]                # costumbres de fijos
    ocupado = Counter()
    sal = lambda f, t: (t >= 1 and guardia[f][t - 1] and dow[t - 1] != 5) or (t >= 2 and guardia[f][t - 2] and dow[t - 2] == 5)
    puede = lambda f, s, t: estado[f][t] == "" and fijo[f][t] < 0 and not sal(f, t) and ocupado[s, t] < dem[s][t]
    for tipo, f, s, v in patrones:
        if tipo == "dia":
            elegidos = [t for t in lab if dow[t] == v and puede(f, s, t)]
        else:
            elegidos = []
            for ini in range(0, nD, 7):
                sem = [t for t in lab if ini - dow[0] <= t < ini - dow[0] + 7 and puede(f, s, t)]
                elegidos += rng.sample(sem, min(v, len(sem)))
        for t in elegidos:
            if puede(f, s, t):
                fijo[f][t] = s; ocupado[s, t] += 1
    d.update(estado=estado, guardia=guardia, fijo=fijo, guardias_dia=n)


def semisintetica(base, anio, mes, presion="media", semilla=0, patrones=(), guardias_dia=2, nombre=None):
    """Plantilla de la instancia real `base` con el calendario de anio-mes generado."""
    rng = random.Random(f"semi-{anio}-{mes}-{presion}-{semilla}")
    d = {k: copy.deepcopy(base.d[k]) for k in ("facultativos", "servicios", "idoneidad")}
    n = ((date(anio + mes // 12, mes % 12 + 1, 1)) - date(anio, mes, 1)).days
    d["dias"] = _dias(date(anio, mes, 1), n, festivos(anio))
    abre = [{base.dow[t] for t in range(base.nD) if base.dem[s][t]} for s in range(base.nS)]   # días de la semana en que abre
    plazas = [max(base.dem[s]) for s in range(base.nS)]
    d["demanda"] = [[plazas[s] if x["dow"] in abre[s] and not x["festivo"] else 0 for x in d["dias"]] for s in range(base.nS)]
    _calendario(d, rng, PRESION[presion], guardias_dia, patrones)
    d["nombre"] = nombre or f"semi_{anio}-{mes:02d}_{presion}_s{semilla}"
    d["origen"] = f"semisintética: plantilla {base.nombre}, presión {presion}, semilla {semilla}"
    return Instancia(d)


FAMILIAS = ("ECO", "TAC", "RM", "MAMA", "VAS", "NRI", "TORAX", "NME", "URG", "PED", "ABD", "CARD")


def sintetica(nR, semanas=4, semilla=0, presion="media", densidad=0.30, nombre=None):
    """Departamento de nR facultativos y unos 0,84·nR servicios agrupados por familias; la idoneidad es alta dentro
    de la familia propia y dispersa fuera (densidad = fracción aproximada de idoneidades no nulas)."""
    rng = random.Random(f"sint-{nR}-{semanas}-{presion}-{densidad}-{semilla}")
    nS = max(6, round(0.84 * nR))
    nFam = max(3, nS // 3)
    tam = [2] * nFam
    for _ in range(nS - 2 * nFam):
        tam[rng.randrange(nFam)] += 1
    serv, fam_s = [], []
    for k in range(nFam):
        prios = [0 if rng.random() < 0.6 else 1] + sorted(rng.choices(range(1, 7), (6, 2, 5, 4, 1, 1), k=tam[k] - 1))
        for j, p in enumerate(prios):
            tarde = j > 0 and p >= 3 and rng.random() < 0.25
            serv.append({"id": f"S{len(serv) + 1:03d}", "nombre": f"{FAMILIAS[k % len(FAMILIAS)]}{chr(65 + k // len(FAMILIAS)) if nFam > len(FAMILIAS) else ''}{j + 1}{'T' if tarde else ''}", "prioridad": p,
                         "turno": "T" if tarde else "M", "en_objetivo": True})
            fam_s.append(k)
    de_fam = [[s for s in range(nS) if fam_s[s] == k] for k in range(nFam)]
    propio = list(range(nS)) + [None] * (nR - nS)        # un facultativo «de referencia» por servicio y el resto de apoyo
    fam_f = [fam_s[s] if s is not None else rng.choices(range(nFam), tam)[0] for s in propio]
    orden = list(range(nR)); rng.shuffle(orden)
    q = max(0.0, (densidad - 1 / nFam) / (0.7 * (1 - 1 / nFam)))
    fac, ido = [None] * nR, [None] * nR
    for pos, f in enumerate(orden):
        s0, k0 = propio[pos], fam_f[pos]
        fila = [0] * nS
        for s in de_fam[k0]:
            fila[s] = 3 if s == s0 else rng.choices((3, 2, 1), (6, 3, 1))[0]
        for k in range(nFam):
            if k != k0 and rng.random() < q:
                for s in de_fam[k]:
                    if rng.random() < 0.7:
                        fila[s] = rng.choices((1, 2, 3), (50, 35, 15))[0]
        turno = rng.choices(("M", "M/T", "T"), (60, 37, 3))[0]
        if s0 is not None:
            turno = "M/T" if serv[s0]["turno"] == "T" else ("M" if turno == "T" else turno)
        fac[f] = {"id": f"R{f + 1:03d}", "jornada": rng.choices((1.0, 0.8, 0.7, 0.6, 0.4), (55, 15, 6, 21, 3))[0], "turno": turno,
                  "guardias": rng.random() < 0.6, "titular": s0 if s0 is not None and rng.random() < 0.85 else None,
                  "suplente1": None, "suplente2": None, "suplente3": None}
        ido[f] = fila
    for nivel, p, minimo in (("suplente1", 0.45, 2), ("suplente2", 0.20, 2), ("suplente3", 0.05, 1)):
        for s in range(nS):
            if rng.random() < p:
                cand = [f for f in range(nR) if ido[f][s] >= minimo and fac[f][nivel] is None
                        and all(fac[f][k] != s for k in NIVELES) and (fac[f]["turno"] == "M/T" or fac[f]["turno"] == serv[s]["turno"])]
                if cand:
                    fac[rng.choice(cand)][nivel] = s
    inicio = date(2027, 1, 4)                            # un lunes
    fest = {inicio + timedelta(days=i) for i in range(7 * semanas) if i % 7 < 5 and rng.random() < 0.03}
    dias = _dias(inicio, 7 * semanas, fest)
    abre = [set(range(5)) if serv[s]["prioridad"] < 3 or rng.random() > 0.15 else set(rng.sample(range(5), rng.randint(1, 3))) for s in range(nS)]
    dem = [[1 if x["dow"] in abre[s] and not x["festivo"] else 0 for x in dias] for s in range(nS)]
    d = {"nombre": nombre or f"sint_R{nR:03d}_W{semanas:02d}_{presion}_s{semilla}",
         "origen": f"sintética: nR={nR}, semanas={semanas}, presión={presion}, densidad={densidad}, semilla={semilla}",
         "dias": dias, "facultativos": fac, "servicios": serv, "idoneidad": ido, "demanda": dem}
    _calendario(d, rng, PRESION[presion], max(1, round(2 * nR / 31)))
    return Instancia(d)

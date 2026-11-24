"""Experimentos de formación (reanudables; cada bloque escribe en resultados/formacion_*.csv).

    python exp_formacion.py reales      # elige en enero-mayo de 2025; evalúa en los 9 meses reales y en las 36 semisintéticas
    python exp_formacion.py sinteticas  # en cada sintética de 8 semanas: elige en las semanas 1-4 y evalúa en las 5-8
"""
import csv
import glob
import sys
from pathlib import Path

from radplan import Config, Instancia, construir, evaluar, resolver
from radplan.formacion import aplicar, candidatos, describir, elegir

AQUI = Path(__file__).resolve().parent
RES = AQUI / "resultados"
CFG = Config(cobertura="blanda")
KPI = ["demanda", "servicios", "apoyos", "obligatorios_sin_cubrir", "idoneidad0", "idoneidad1", "idoneidad2", "idoneidad3"] + [f"prioridad{p}" for p in range(7)]
ETIQ = {(1,): "1a2", (0, 1): "01a2"}


class Tabla:
    def __init__(self, ruta, campos, clave):
        self.ruta, self.campos, self.clave = ruta, campos, clave
        self.hechos = set()
        if ruta.exists():
            with open(ruta, newline="", encoding="utf-8") as fh:
                self.filas = list(csv.DictReader(fh))
            self.hechos = {tuple(r[c] for c in clave) for r in self.filas}
        else:
            self.filas = []
            with open(ruta, "w", newline="", encoding="utf-8") as fh:
                csv.DictWriter(fh, campos).writeheader()

    def hecho(self, **k):
        return tuple(str(k[c]) for c in self.clave) in self.hechos

    def add(self, **fila):
        with open(self.ruta, "a", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, self.campos, extrasaction="ignore").writerow(fila)
        self.hechos.add(tuple(str(fila[c]) for c in self.clave))
        self.filas.append({k: str(v) for k, v in fila.items()})


def medir(I, mejoras, tl=120):
    I2 = aplicar(I, mejoras)
    r = resolver(construir(I2, CFG), tl=tl, hilos=2)
    ev = evaluar(I2, r["sol"], CFG)
    return dict(estado=r["estado"], objetivo=round(r["objetivo"], 3), violaciones=ev["n_violaciones"],
                **{k: ev["kpi"].get(k, 0) for k in KPI})


def leer_mejoras(txt):
    return [tuple(map(int, p.split("-"))) for p in txt.split()] if txt else []


def reales():
    R = [Instancia.cargar(p) for p in sorted(glob.glob(str(AQUI / "instancias/reales/*_IF.json")))]
    S = [Instancia.cargar(p) for p in sorted(glob.glob(str(AQUI / "instancias/semi/*.json")))]
    train = R[:5]
    grupo = {I.nombre: ("real_train" if i < 5 else "real_test") for i, I in enumerate(R)}
    grupo.update({I.nombre: "semi_" + I.nombre.split("_")[2] for I in S})
    sel = Tabla(RES / "formacion_seleccion.csv", ["entrenamiento", "desde", "k", "candidatos", "estado", "objetivo", "cota", "gap", "variables",
                                                  "restricciones", "t_construir", "t_resolver", "mejoras", "descripcion"], ("entrenamiento", "desde", "k"))
    eva = Tabla(RES / "formacion_eval.csv", ["entrenamiento", "desde", "k", "instancia", "grupo", "estado", "objetivo", "violaciones"] + KPI,
                ("entrenamiento", "desde", "k", "instancia"))
    planes = [("ene-may", train, desde, k) for desde in ((1,), (0, 1)) for k in list(range(0, 11)) + [15, 20, "todas"]]
    planes += [("jun-sep", R[5:], (0, 1), k) for k in (3, 5, 10)]            # referencia: elegir conociendo los meses de prueba
    media = [I for I in S if "_media_" in I.nombre]
    mixto = [I for i, I in enumerate(sorted(S, key=lambda I: I.nombre)) if i % 3 == (i // 3) % 3]   # 12 meses, 4 de cada presión
    for nombre, tr in (("reales9", R), ("semi_media12", media), ("semi_mixto12", mixto)):
        planes += [(nombre, tr, (0, 1), k) for k in (2, 3, 5, 10)]
    for nombre, tr, desde, k in planes:
        d = ETIQ[desde]
        if not sel.hecho(entrenamiento=nombre, desde=d, k=k):
            if k == "todas":
                mej = candidatos(R[0], desde)
                sel.add(entrenamiento=nombre, desde=d, k=k, candidatos=len(mej), estado="-", mejoras=" ".join(f"{f}-{s}" for f, s in mej))
            else:
                mej, info = elegir(tr, k, CFG, desde, tl=240, hilos=2)
                sel.add(entrenamiento=nombre, desde=d, **{a: (round(b, 4) if isinstance(b, float) else b) for a, b in info.items() if a != "soluciones"},
                        mejoras=" ".join(f"{f}-{s}" for f, s in mej), descripcion=describir(R[0], mej))
                print(nombre, d, k, info["estado"], info["t_resolver"], describir(R[0], mej), flush=True)
        mej = leer_mejoras(next(r["mejoras"] for r in sel.filas if (r["entrenamiento"], r["desde"], r["k"]) == (nombre, d, str(k))))
        for I in R + S:
            if not eva.hecho(entrenamiento=nombre, desde=d, k=k, instancia=I.nombre):
                eva.add(entrenamiento=nombre, desde=d, k=k, instancia=I.nombre, grupo=grupo[I.nombre], **medir(I, mej))
        print("evaluado", nombre, d, k, flush=True)


def recortar(I, a, b, nombre):
    """Días [a, b) de la instancia; los salientes de guardias anteriores a `a` pasan a ser estado 'SG'."""
    d = dict(I.d)
    d["nombre"] = nombre
    d["dias"] = I.dias[a:b]
    for k in ("demanda", "estado", "guardia", "fijo"):
        d[k] = [list(fila[a:b]) for fila in I.d[k]]
    d["guardias_dia"] = I.guardias_dia[a:b]
    for f in range(I.nF):
        for t in range(a, min(b, a + 2)):
            if I.saliente(f, t) and not I.saliente(f, t, [[0] * a + list(g[a:]) for g in I.guardia]) and d["estado"][f][t - a] == "":
                d["estado"][f][t - a] = "SG"
    d.pop("referencia", None)
    return Instancia(d)


def sinteticas(max_nR=120, tl=180):
    tab = Tabla(RES / "formacion_sinteticas.csv", ["instancia", "nF", "nS", "desde", "k", "candidatos", "variables", "restricciones", "estado", "gap",
                                                   "t_construir", "t_resolver", "parte", "mejoras_aplicadas", "objetivo", "violaciones"] + KPI,
                ("instancia", "desde", "parte", "mejoras_aplicadas"))
    for ruta in sorted(glob.glob(str(AQUI / "instancias/sinteticas/*_W08_*.json"))):
        I = Instancia.cargar(ruta)
        if I.nF > max_nR:
            continue
        A, B = recortar(I, 0, 28, I.nombre + "_sem1-4"), recortar(I, 28, 56, I.nombre + "_sem5-8")
        k = round(0.15 * I.nF)
        for desde in ((1,), (0, 1)):
            d = ETIQ[desde]
            if tab.hecho(instancia=I.nombre, desde=d, parte="prueba", mejoras_aplicadas="todas"):
                continue
            mej, info = elegir([A], k, CFG, desde, tl=tl, hilos=2)
            comun = dict(instancia=I.nombre, nF=I.nF, nS=I.nS, desde=d, k=k, **{a: (round(b, 4) if isinstance(b, float) else b) for a, b in info.items()
                                                                              if a in ("candidatos", "variables", "restricciones", "estado", "gap", "t_construir", "t_resolver")})
            print(I.nombre, d, k, info["estado"], info.get("gap"), info["t_resolver"], flush=True)
            for parte, J in (("entrenamiento", A), ("prueba", B)):
                for nom, m in (("ninguna", []), ("elegidas", mej or []), ("todas", candidatos(I, desde))):
                    tab.add(**{**medir(J, m), **comun}, parte=parte, mejoras_aplicadas=nom)


if __name__ == "__main__":
    {"reales": reales, "sinteticas": sinteticas}[sys.argv[1]](*map(int, sys.argv[2:]))

"""Conversión de los libros de SolverStudio al formato de instancia (anonimizando a los facultativos)."""
import warnings
from datetime import date
from pathlib import Path

from .instancia import NIVELES, Instancia

ESTADOS = {"RJ": ("RJ", 0), "P": ("P", 0), "SG": ("SG", 0), "E": ("E", 0), "G": ("", 1), "G_RJ": ("RJ", 1)}


def norm(v):
    return " ".join(str(v).upper().split()) if v not in (None, 0) else ""


def version_modelo(nombre):
    """Versión del modelo incrustado: hasta v13 la idoneidad 0 estaba prohibida también en obligatorios."""
    return "v15" if "v15" in nombre else "v14" if "v14" in nombre else "v13"


def convertir(ruta, nombre=None):
    """Devuelve (Instancia, avisos). Lee el texto de 'Especificaciones', no las fórmulas de 'Fijos_cod',
    y recorta el horizonte a los días reales del mes."""
    import openpyxl
    ruta = Path(ruta)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(ruta, data_only=True)
    F, S, I_, X, SOL, E = (wb[n] for n in ("Facultativos", "Servicios", "Idoneidad", "Fijos_cod", "Solucion", "Especificaciones"))
    num = lambda v: int(v) if isinstance(v, (int, float)) else 0
    nF, nS, nD = num(F["B1"].value), num(S["B1"].value), num(X["B3"].value)
    anio, mes = num(S["O5"].value), num(S["O4"].value)
    avisos = []

    serv, ids = [], {}
    for s in range(nS):
        nom = " ".join(str(S.cell(16 + s, 2).value).split())
        serv.append({"id": f"S{s + 1:02d}", "nombre": nom, "prioridad": num(S.cell(16 + s, 4).value),
                     "turno": str(S.cell(16 + s, 5).value).strip().upper(), "en_objetivo": s != 20})   # el modelo excluye el servicio 21
        ids[norm(nom)] = s
    if nS > 20 and not serv[20]["nombre"].upper().startswith("ALM"):
        avisos.append(f"el servicio 21 ({serv[20]['nombre']}) está fuera del objetivo y no es Almansa")
    dias = []
    for d in range(nD):
        f = date(anio, mes, d + 1)
        dias.append({"fecha": f.isoformat(), "dow": f.weekday(), "festivo": num(S.cell(13, 7 + d).value) == 1})
    dem = [[num(S.cell(16 + s, 7 + d).value) for d in range(nD)] for s in range(nS)]

    fac = []
    for f in range(nF):
        r = 4 + f
        j = F.cell(r, 4).value
        x = {"id": f"R{f + 1:02d}", "jornada": float(j) if isinstance(j, (int, float)) else 1.0,
             "turno": str(F.cell(r, 11).value or "M/T").strip().upper(), "guardias": norm(F.cell(r, 7).value) == "PF"}
        for k, col in zip(NIVELES, (12, 13, 14, 15)):
            t = norm(F.cell(r, col).value)
            x[k] = ids.get(t)
            if t and t not in ids:
                avisos.append(f"{x['id']}: servicio '{t}' de la columna {k} no existe")
            if (x[k] + 1 if x[k] is not None else 0) != num(X.cell(8 + f, 4 + NIVELES.index(k)).value):
                avisos.append(f"{x['id']}: {k} no coincide con Fijos_cod")
        fac.append(x)
    ido = [[num(I_.cell(9 + f, 4 + s).value) for s in range(nS)] for f in range(nF)]

    estado = [[""] * nD for _ in range(nF)]
    guardia = [[0] * nD for _ in range(nF)]
    fijo = [[-1] * nD for _ in range(nF)]
    for f in range(nF):
        for d in range(nD):
            t = norm(E.cell(12 + f, 5 + d).value)
            if not t:
                continue
            if t in ESTADOS:
                estado[f][d], guardia[f][d] = ESTADOS[t]
            elif t in ids:
                fijo[f][d] = ids[t]
            elif t.startswith("G_") and t[2:] in ids:
                guardia[f][d], fijo[f][d] = 1, ids[t[2:]]
            else:
                avisos.append(f"{fac[f]['id']} día {d + 1}: código '{t}' no reconocido")
    sol = [[num(SOL.cell(7 + f, 5 + d).value) - 1 for d in range(nD)] for f in range(nF)]
    d = {"nombre": nombre or ruta.stem, "origen": f"real: {ruta.name}", "dias": dias, "facultativos": fac, "servicios": serv,
         "idoneidad": ido, "demanda": dem, "estado": estado, "guardia": guardia, "fijo": fijo,
         "guardias_dia": [sum(guardia[f][t] for f in range(nF)) for t in range(nD)],
         "referencia": {"modelo_excel": version_modelo(ruta.name), "asig": sol}}
    return Instancia(d), avisos

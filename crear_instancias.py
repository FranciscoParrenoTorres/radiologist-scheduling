"""Crea todo el banco de instancias en ./instancias (reales anonimizadas, semisintéticas y sintéticas).

    python crear_instancias.py
"""
from pathlib import Path

from radplan.excel import convertir
from radplan.generador import inferir_patrones, semisintetica, sintetica
from radplan.validar import reparar, validar

AQUI = Path(__file__).resolve().parent
SOL, OUT = AQUI.parent / "Soluciones", AQUI / "instancias"
MESES = "enero febrero marzo abril mayo junio julio agosto septiembre".split()

reales = []
for libro in sorted(SOL.rglob("*.xlsx")):
    if "_ns" in libro.name or "_nt" in libro.name:          # variantes: ahora son opciones del modelo
        continue
    mes = next(i + 1 for i, m in enumerate(MESES) if m in libro.name.lower())
    ido = "II" if libro.name.startswith("II") else "IF"
    I, avisos = convertir(libro, nombre=f"real_2025-{mes:02d}_{ido}")
    cambios = reparar(I)
    err, _ = validar(I)
    I.d["referencia"]["valida"] = not cambios and "JULIO" not in libro.name
    I.guardar(OUT / "reales" / f"{I.nombre}.json")
    print(I.nombre, "|", "; ".join(avisos + cambios + err) or "ok")
    if ido == "IF":
        reales.append(I)

patrones = inferir_patrones(reales)
print("patrones de fijos:", [(t, reales[0].fac[f]["id"], reales[0].serv[s]["nombre"], v) for t, f, s, v in patrones])
base = reales[0]
for mes in range(1, 13):
    for presion in ("baja", "media", "alta"):
        semisintetica(base, 2026, mes, presion, 0, patrones).guardar(OUT / "semi" / f"semi_2026-{mes:02d}_{presion}_s0.json")
for nR in (20, 31, 45, 60, 90, 120, 180, 240):
    for semanas in (4, 8, 13):
        for semilla in range(3):
            I = sintetica(nR, semanas, semilla)
            I.guardar(OUT / "sinteticas" / f"{I.nombre}.json")
print("instancias:", {p.name: len(list(p.glob('*.json'))) for p in sorted(OUT.iterdir())})

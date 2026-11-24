"""Regresión contra los libros de Excel: el modelo en Python, configurado como el de SolverStudio,
debe dar el mismo óptimo que la solución guardada (cuando esta es válida para los datos del libro).

    pytest -q tests
"""
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from radplan import Config, construir, evaluar, resolver          # noqa: E402
from radplan.excel import convertir                                # noqa: E402

LIBROS = sorted((RAIZ / "excel").rglob("*.xlsx"))
# libros cuya solución guardada no corresponde a sus datos (ver validar.py)
CADUCADAS = ("JULIO", "SEPTIEMBRE")


def config_excel(I):
    return Config(jerarquia="excel", idoneidad0="prohibida" if I.ref["modelo_excel"] == "v13" else "penalizada")


@pytest.mark.parametrize("libro", LIBROS, ids=lambda p: p.stem)
def test_reproduce_excel(libro):
    I, avisos = convertir(libro)
    assert not avisos, avisos
    cfg = config_excel(I)
    guardada = evaluar(I, {"asig": I.ref["asig"], "guardia": I.guardia}, cfg)
    if any(c in libro.name for c in CADUCADAS):
        assert guardada["n_violaciones"] > 0
        return
    assert guardada["n_violaciones"] == 0, guardada["violaciones"]
    r = resolver(construir(I, cfg))
    assert r["estado"] == "optimo"
    assert round(r["objetivo"]) == round(guardada["objetivo"])
    propia = evaluar(I, r["sol"], cfg)
    assert propia["n_violaciones"] == 0, propia["violaciones"]
    assert abs(propia["objetivo"] - r["objetivo"]) < 1e-6


@pytest.mark.parametrize("mes", ["enero", "febrero", "marzo", "abril", "mayo"])
def test_variantes_son_opciones(mes):
    """Los libros _ns3, _ns2ns3... equivalen a la opción 'niveles' sobre el libro base."""
    carpeta = next(p for p in (RAIZ / "excel").iterdir() if mes in p.name)
    base, _ = convertir(carpeta / f"IF_{mes}_2025.xlsx")
    for sufijo, cfg in (("ns3", dict(niveles=2)), ("ns2ns3", dict(niveles=1)), ("ns1ns2ns3", dict(niveles=0)),
                        ("ntns1ns2ns3", dict(jerarquia="no"))):
        var, _ = convertir(carpeta / f"IF_{mes}_2025_{sufijo}.xlsx")
        if sufijo == "ntns1ns2ns3" and any(x["titular"] is not None for x in var.fac):
            cfg = dict(niveles=0)      # en el libro de enero no se llegaron a quitar los titulares
        a = resolver(construir(base, Config(**{"jerarquia": "excel", "idoneidad0": "prohibida", **cfg})))
        b = resolver(construir(var, Config(jerarquia="excel", idoneidad0="prohibida")))
        assert round(a["objetivo"]) == round(b["objetivo"]), sufijo

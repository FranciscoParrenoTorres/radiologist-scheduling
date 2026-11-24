"""Anonimiza los libros de SolverStudio del servicio sin abrirlos con Excel (edita el XML del .xlsx).

    python anonimizar_excel.py CARPETA_ORIGEN CARPETA_DESTINO

Para cada libro:
  * los apellidos (Facultativos!B) pasan a RAD01, RAD02... y los acrónimos (Facultativos!C) a R01, R02...,
    tanto en las celdas como en los valores en caché de las fórmulas que los muestran;
  * la actividad no asistencial (Facultativos!F) pasa a "SI", salvo la marca ALMANSA, que usa el modelo;
  * se eliminan el autor, el último usuario, la ruta del fichero y la configuración de impresora.
Las fórmulas, los formatos y el modelo de SolverStudio incrustado (customXml) no se tocan.
Al terminar se comprueba que en ninguna parte del libro queda un apellido o un acrónimo.
"""
import html
import re
import sys
import zipfile
from pathlib import Path

NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
FILAS = range(4, 44)                       # filas de la hoja Facultativos


def texto_si(si):
    return html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)))


def hoja(z, nombre):
    """Ruta dentro del zip de la hoja con ese nombre."""
    wb = z.read("xl/workbook.xml").decode("utf8")
    rid = re.search(r'<sheet\b[^>]*name="%s"[^>]*r:id="([^"]+)"' % re.escape(nombre), wb).group(1)
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf8")
    for rel in re.findall(r"<Relationship\b[^>]*>", rels):
        if 'Id="%s"' % rid in rel:
            return "xl/" + re.search(r'Target="([^"]+)"', rel).group(1).lstrip("/").removeprefix("xl/")
    raise KeyError(nombre)


def celdas(xml):
    """{referencia: (tipo, valor)} de las celdas con valor de una hoja."""
    out = {}
    for attrs, cuerpo in re.findall(r"<c\b([^>]*?)(?:/>|>(.*?)</c>)", xml, re.S):
        ref = re.search(r'\br="([A-Z]+\d+)"', attrs).group(1)
        t = re.search(r'\bt="(\w+)"', attrs)
        v = re.search(r"<v>(.*?)</v>", cuerpo or "", re.S)
        if v:
            out[ref] = (t.group(1) if t else "n", html.unescape(v.group(1)))
    return out


def anonimizar(origen, destino):
    z = zipfile.ZipFile(origen)
    partes = {n: z.read(n) for n in z.namelist()}
    ss = partes["xl/sharedStrings.xml"].decode("utf8")
    items = re.findall(r"<si>.*?</si>|<si/>", ss, re.S)
    textos = [texto_si(s) for s in items]
    ruta_fac = hoja(z, "Facultativos")
    fac = celdas(partes[ruta_fac].decode("utf8"))

    def cadena(ref):
        t, v = fac.get(ref, ("", ""))
        return textos[int(v)] if t == "s" else (v if t == "str" else "")

    # 1. correspondencia nombre -> seudónimo
    mapa = {}
    for k, fila in enumerate(FILAS, start=1):
        for col, pref in (("B", "RAD"), ("C", "R")):
            nombre = cadena(f"{col}{fila}")
            if nombre.strip():
                assert mapa.setdefault(nombre, f"{pref}{k:02d}") == f"{pref}{k:02d}", f"nombre repetido: fila {fila}"
    assert mapa, "no hay facultativos"
    no_asist = {cadena(f"F{f}") for f in FILAS} - {""}
    no_asist = {t for t in no_asist if "ALMANSA" not in t.upper()}
    for t in no_asist:                      # esas cadenas solo deben usarse en Facultativos!F
        i = textos.index(t)
        for n, datos in partes.items():
            if n.startswith("xl/worksheets/sheet"):
                usos = [r for r, (tp, v) in celdas(datos.decode("utf8")).items() if tp == "s" and int(v) == i]
                assert all(n == ruta_fac and r.startswith("F") for r in usos), (t, n, usos)
        mapa[t] = "SI"

    # 2. cadenas compartidas
    nuevo = lambda s: "<si><t>%s</t></si>" % html.escape(s, quote=False)
    it = iter(items)
    ss = re.sub(r"<si>.*?</si>|<si/>", lambda m: (lambda s: nuevo(mapa[texto_si(s)]) if texto_si(s) in mapa else s)(next(it)),
                ss, flags=re.S)
    partes["xl/sharedStrings.xml"] = ss.encode("utf8")

    # 3. valores en caché de las fórmulas, impresora
    def cache(m):
        v = html.unescape(m.group(2))
        return m.group(1) + (html.escape(mapa[v], quote=False) if v in mapa else m.group(2)) + m.group(3)

    for n in list(partes):
        if n.startswith("xl/worksheets/sheet"):
            x = partes[n].decode("utf8")
            x = re.sub(r'(<c\b[^>]*\bt="str"[^>]*>(?:(?!</c>).)*?<v>)([^<]*)(</v>)', cache, x, flags=re.S)
            x = re.sub(r'(<pageSetup\b[^>]*?)\s+r:id="[^"]*"', r"\1", x)
            partes[n] = x.encode("utf8")
        elif n.startswith("xl/printerSettings/"):
            del partes[n]
        elif n.startswith("xl/worksheets/_rels/"):
            x = re.sub(r"<Relationship\b[^>]*printerSettings[^>]*/>", "", partes[n].decode("utf8"))
            if "<Relationship " in x:
                partes[n] = x.encode("utf8")
            else:
                del partes[n]

    # 4. metadatos
    core = partes["docProps/core.xml"].decode("utf8")
    core = re.sub(r"<dc:creator>.*?</dc:creator>", "<dc:creator></dc:creator>", core, flags=re.S)
    core = re.sub(r"<cp:lastModifiedBy>.*?</cp:lastModifiedBy>", "<cp:lastModifiedBy></cp:lastModifiedBy>", core, flags=re.S)
    partes["docProps/core.xml"] = core.encode("utf8")
    wb = partes["xl/workbook.xml"].decode("utf8")
    wb, k = re.subn(r"<mc:AlternateContent\b(?:(?!</mc:AlternateContent>).)*absPath.*?</mc:AlternateContent>", "", wb, flags=re.S)
    partes["xl/workbook.xml"] = wb.encode("utf8")

    # 4b. comentarios del modelo incrustado que citan a alguien por su apellido
    for n in list(partes):
        if n.startswith("customXml/") and partes[n][:2] not in (b"\xff\xfe", b"\xfe\xff"):
            x = partes[n].decode("utf8")
            for nombre, seud in mapa.items():
                if seud != "SI" and len(nombre) >= 5:
                    x = re.sub(r"(?<![A-Za-zÁÉÍÓÚÑáéíóúñ_])%s(?![A-Za-zÁÉÍÓÚÑáéíóúñ_])" % re.escape(nombre), seud, x, flags=re.I)
            partes[n] = x.encode("utf8")

    # 5. comprobación: no queda ningún nombre en ninguna parte del libro
    nombres = [n for n in mapa if mapa[n] != "SI"]
    for n, datos in partes.items():
        try:
            x = datos.decode("utf16" if datos[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf8")
        except UnicodeDecodeError:
            x = datos.decode("latin1")
        x = html.unescape(x)
        for nombre in nombres:
            patron = r"(?<![A-Za-zÁÉÍÓÚÑáéíóúñ_])%s(?![A-Za-zÁÉÍÓÚÑáéíóúñ_])" % re.escape(nombre)
            if len(nombre) >= 5:
                assert not re.search(patron, x, re.I), (origen.name, n, nombre)
            else:                           # los acrónimos cortos solo se buscan como valor completo de una celda
                assert f">{nombre}<" not in x, (origen.name, n, nombre)
        for marca in ("absPath", "printerSettings"):
            assert marca not in x or n == "[Content_Types].xml", (origen.name, n, marca)

    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as out:
        for n in z.namelist():              # mismo orden que el original
            if n in partes:
                out.writestr(n, partes[n])
    return len(nombres)


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    for libro in sorted(src.rglob("*.xlsx")):
        salida = dst / libro.relative_to(src).with_name(re.sub(r"\s*\(\d+\)", "", libro.name))
        print(salida.relative_to(dst), anonimizar(libro, salida), "cadenas sustituidas")

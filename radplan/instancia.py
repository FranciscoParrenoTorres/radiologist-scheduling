"""Formato de instancia, independiente de Excel (un JSON por instancia).

Índices desde 0. Campos:
  dias          [{fecha, dow (0=lunes..6=domingo), festivo}]
  facultativos  [{id, jornada, turno ('M'|'T'|'M/T'), guardias (hace guardias),
                  titular, suplente1, suplente2, suplente3 (índice de servicio o null)}]
  servicios     [{id, nombre, prioridad (0 = obligatorio .. 6), turno ('M'|'T'), en_objetivo}]
  idoneidad     [facultativo][servicio]  0..3
  demanda       [servicio][dia]          facultativos requeridos (0 = cerrado)
  estado        [facultativo][dia]       '' disponible | 'RJ' | 'P' | 'SG' | 'E'
  guardia       [facultativo][dia]       1 si tiene guardia prefijada
  fijo          [facultativo][dia]       servicio prefijado o -1
  guardias_dia  [dia]                    guardias que hay que cubrir (solo si las decide el modelo)
  referencia    opcional: solución guardada en el Excel de origen
"""
import json
from pathlib import Path

NIVELES = ("titular", "suplente1", "suplente2", "suplente3")
CLAVES = ("nombre", "origen", "dias", "facultativos", "servicios", "idoneidad", "demanda", "estado",
          "guardia", "fijo", "guardias_dia", "referencia")


class Instancia:
    def __init__(self, d):
        self.d = d
        self.nombre = d["nombre"]
        self.dias, self.fac, self.serv = d["dias"], d["facultativos"], d["servicios"]
        self.ido, self.dem, self.estado = d["idoneidad"], d["demanda"], d["estado"]
        self.guardia, self.fijo, self.guardias_dia = d["guardia"], d["fijo"], d["guardias_dia"]
        self.ref = d.get("referencia")
        self.nF, self.nS, self.nD = len(self.fac), len(self.serv), len(self.dias)
        self.dow = [x["dow"] for x in self.dias]
        self.laborable = [any(self.dem[s][t] for s in range(self.nS)) for t in range(self.nD)]

    def compatible(self, f, s):
        tf = self.fac[f]["turno"]
        return tf == "M/T" or tf == self.serv[s]["turno"]

    def destino_saliente(self, t):
        """Día de descanso que genera una guardia el día t (sábado -> lunes; resto -> día siguiente)."""
        return t + 2 if self.dow[t] == 5 else t + 1

    def saliente(self, f, t, guardia=None):
        g = self.guardia if guardia is None else guardia
        return bool((t >= 1 and g[f][t - 1] and self.dow[t - 1] != 5) or (t >= 2 and g[f][t - 2] and self.dow[t - 2] == 5))

    @staticmethod
    def cargar(ruta):
        return Instancia(json.loads(Path(ruta).read_text(encoding="utf-8")))

    def guardar(self, ruta):
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        filas = [f'"{k}": {json.dumps(self.d[k], ensure_ascii=False)}' for k in CLAVES if k in self.d]
        ruta.write_text("{\n" + ",\n".join(filas) + "\n}\n", encoding="utf-8")
        return ruta

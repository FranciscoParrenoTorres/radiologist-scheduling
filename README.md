# radiologist-scheduling

Code, anonymized instances and results for the paper on the monthly assignment of staff radiologists to the
services of a radiology department (integer programming model, with on-call duties, continuity and training
extensions). The code and its comments are written in Spanish.

## Contents

| Path | Description |
|---|---|
| `radplan/` | Python package: instance format (`instancia.py`), Pyomo model with all its variants (`modelo.py`), on-call and training extensions (`guardias.py`, `formacion.py`), solver-independent solution checker (`comprobar.py`), instance generator (`generador.py`), validation (`validar.py`) and conversion from the hospital workbooks (`excel.py`). |
| `instancias/reales/` | 14 real instances (January–September 2025, initial `II` and revised `IF` suitability matrices), with the radiologists anonymized (`R01`, `R02`, ...). |
| `instancias/semi/` | 36 semi-synthetic instances: real staff with a new calendar and three levels of absence pressure. |
| `instancias/sinteticas/` | 72 synthetic instances of different sizes. |
| `resultados/` | CSV files with the results reported in the paper. |
| `exp_*.py` | Scripts that run the experiments and write the files in `resultados/`. |
| `crear_instancias.py`, `prototipo.py` | Build the instance set from the hospital workbooks (see the note below). |
| `tests/` | Regression tests against the hospital workbooks. |

## Requirements

Python 3.10 or later and

```
pip install -r requirements.txt
```

The model is solved with HiGHS by default; CBC, Gurobi or any other solver available from Pyomo can also be used.

## Usage

```python
from radplan import Config, Instancia, construir, resolver, evaluar

I = Instancia.cargar("instancias/reales/real_2025-01_IF.json")
```

To reproduce the main tables of the paper:

```
python exp_articulo.py        # -> resultados/articulo.csv
python exp_guardias.py instancias/reales/*_IF.json --tl 120 --salida resultados/guardias_cuotas_reales.csv
python exp_formacion.py       # -> resultados/formacion_*.csv
```

## Instance format

Each instance is a JSON file with the fields `dias` (calendar), `facultativos` (radiologists: working time,
shift, on-call duties and the services of which they are holder or substitute), `servicios` (services: priority
and shift), `idoneidad` (suitability matrix, 0–3), `demanda`, `estado` (absences), `guardia`, `fijo`
(fixed assignments) and, for the real instances, `referencia` (the solution used by the department).

## Note on the original data

The original workbooks of the radiology department contain personal data and are not distributed. Therefore
`crear_instancias.py`, `prototipo.py` and `tests/` cannot be run from this repository; they are included only
to document how the anonymized instances were obtained and checked.

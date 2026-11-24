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
| `excel/` | The 34 Excel workbooks used by the department (operational version), anonymized, with the embedded SolverStudio model and the stored solutions. See [`excel/README.md`](excel/README.md) for a description of every sheet. |
| `anonimizar_excel.py` | Script that anonymized the workbooks. |
| `crear_instancias.py`, `prototipo.py` | Build the instance set from the workbooks in `excel/`. |
| `tests/` | Regression tests: the Python model reproduces the optimal value stored in each workbook. |

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

## Operational version: Excel and SolverStudio

The department plans each month with an Excel workbook. The data are typed in ordinary sheets, the model is
written in [Pyomo](https://www.pyomo.org) and stored inside the workbook, and
[SolverStudio](https://solverstudio.org) (a free Excel add-in) connects both: it reads the data from the sheets,
runs the model with the CBC solver and writes the solution back into the workbook. No programming is needed
to use it.

### Installation (Windows only)

1. Excel 2019 or Microsoft 365 for Windows. SolverStudio does not work on Mac.
2. Download SolverStudio from <https://solverstudio.org/download-install/>, extract the zip file and run
   `Setup.exe`. Then, in Excel, go to *File > Options > Add-ins > COM Add-ins > Go* and tick *SolverStudio*.
   A SolverStudio group appears in the *Data* tab.
3. Install Python from <https://www.python.org> (adding it to the `PATH`) and then Pyomo with
   `pip install pyomo`.

### How the workbook and the model are connected

SolverStudio links named ranges of the workbook (*data items*) with the sets, parameters and variables of the
model that have the same name. They can be seen and edited with *Data > SolverStudio > Edit Data*.

| Data item | Range | Content |
|---|---|---|
| `facultativos`, `servicios`, `dias` | `Facultativos!A4:A43`, `Servicios!A16:A50`, `Fijos_cod!H7:AL7` | Index sets |
| `numero_facultativos`, `numero_servicios`, `numero_dias` | `Facultativos!B1`, `Servicios!B1`, `Fijos_cod!B3` | Real sizes |
| `prioridades`, `turno_serv`, `demanda` | `Servicios!D16:D50`, `E16:E50`, `G16:AK50` | Priority, shift and daily demand of each service |
| `idoneidad` | `Idoneidad!D9:AL48` | Suitability matrix |
| `turno_facultativos` | `Facultativos!K4:K43` | Shift of each radiologist |
| `titular`, `suplente`, `suplente2`, `suplente3` | `Fijos_cod!D8:G47` | Holder and substitute services |
| `fijos`, `tipo_dia`, `almansa` | `Fijos_cod!H8:AL47`, `H6:AL6`, `BC10:BC49` | Coded absences, on-call duties and fixed assignments; day of the week; radiologists of the external agreement |
| `solucion`, `coste`, `avisos` | `Solucion!E7:AI46`, `A4:B4`, `AO6:AO65` | Output: service assigned to each radiologist and day, objective value, warnings |

The model is attached to the sheet `Facultativos`, so **this sheet must be the active one** when the model is
shown or solved; otherwise SolverStudio reports an error.

The model maximizes the sum, over all assignments, of the suitability of the radiologist plus 7 minus the
priority of the service. Its constraints are: mandatory services (priority 0) must be covered and the others
cannot exceed their demand; at most one service per radiologist and day; no service during absences or
post-call rest; suitability and shift compatibility; fixed assignments; and the holder/substitute rule
(a service can only be given to another radiologist if its holder, and then its substitutes, are not
available).

### Solving a month

1. Open one of the workbooks in `excel/`, for instance `2025-05_mayo/IF_mayo_2025.xlsx`, and go to the sheet
   `Facultativos`.
2. *Data > SolverStudio > Show Model* shows the Pyomo code. *Solve Model* runs it. The window *Model Output*
   shows the progress and ends with `Status: Optimal`. The model also prints its own messages, for example when
   a radiologist is fixed to a service for which he or she has no suitability, or to a service that is closed.
3. The solution is shown in `Sol_Facultativo`, `Sol_Servicio` and `Sol_Dia`.

### Planning a new month

1. Save the workbook of the previous month with a new name and set the month in `Servicios!O4` (and the year in
   `O5`). Dates and weekdays are recomputed.
2. In `Servicios`, mark the holidays in row 13 and type 0 in the cells of the services that are closed on
   particular days. If cells of the demand matrix were overwritten the previous month, restore the formula of
   `G16:AK50` first.
3. In `Especificaciones`, clear `E12:AI51` and type the on-call duties (`G`), leaves (`P`), reduced days (`RJ`),
   post-call rests of day 1 (`SG`) and the assignments that must be fixed (the acronym of the service, or
   `G_<service>`).
4. Solve the model from the sheet `Facultativos` and review the solution. If something has to be changed
   (more fixed assignments, swapped on-call duties, a service opened or closed), edit the data and solve again.

Services are added in the first free row of `Servicios` (acronym, priority, shift, number of radiologists) and
their suitability column is filled in `Idoneidad`. Radiologists are added in the first free row of
`Facultativos` and their row is filled in `Idoneidad`. Nothing has to be changed in the model.

## Note on the data

The radiologists are anonymized in the instances and in the workbooks. The original workbooks contain personal
data and are not distributed.

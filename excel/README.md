# Excel workbooks (operational version)

These are the workbooks used by the radiology department to build the monthly plan. Each workbook contains the
data of one month, the optimization model (embedded with [SolverStudio](https://solverstudio.org)) and the
solution that was obtained. The sheet names, headers and codes are in Spanish, as used in the department.

## Anonymization

The workbooks were anonymized with `../anonimizar_excel.py`, which edits the XML of the `.xlsx` file directly,
so that formulas, formats and the embedded model are kept unchanged:

- surnames are replaced by `RAD01`, `RAD02`, ... and acronyms (initials) by `R01`, `R02`, ..., both in the cells
  and in the cached values of the formulas that display them. Radiologist `RADnn` / `Rnn` is the radiologist
  `Rnn` of the JSON instances in `../instancias/reales/`;
- the description of the non-clinical activity of each radiologist (column F of `Facultativos`) is replaced by
  `SI`, except for the mark `ALMANSA`, which is used by the model;
- author, last user, file path and printer settings are removed from the file metadata;
- a comment of the embedded model that mentioned a radiologist by name now shows the pseudonym.

The script checks that no surname or acronym remains in any part of the file. In addition, converting the
original and the anonymized workbooks with `radplan/excel.py` produces identical instances, and the regression
tests in `../tests/` pass on the anonymized workbooks.

## Files

| Files | Description |
|---|---|
| `2025-0X_<month>/IF_<month>_2025.xlsx` (January–May) | Month solved with the revised suitability matrix. |
| `2025-0X_<month>/II_<month>_2025.xlsx` (January–May) | The same month with the initial suitability matrix. |
| `..._ns3`, `..._ns2ns3`, `..._ns1ns2ns3`, `..._ntns1ns2ns3` | Variants of the `IF` workbook without the third substitute level, without the second and third, without any substitute, and without holders and substitutes. They were used to measure the cost of the holder/substitute rule; in the Python package they are options of the model. In the January `ntns1ns2ns3` workbook the holders were not removed. |
| `Modelo_PlanFacultativos_v13_JUNIO`, `v13_JULIO`, `v14_AGOSTO`, `v15_SEPTIEMBRE` | Workbooks as used in production from June to September. `v13`, `v14` and `v15` are versions of the embedded model: up to `v13` a radiologist with suitability 0 cannot be assigned to any service; from `v14` on, this is allowed in mandatory services with a large penalty. |

In the July and September workbooks the stored solution does not correspond to the data of the workbook
(the data were edited after the last run), so it should not be taken as a reference.

## Sheets

The workbook has room for 40 radiologists, 35 services and 31 days. Unused rows and columns are left empty.

### `Especificaciones` (monthly input)

What is known before planning the month. One row per radiologist (rows 12–51) and one column per day
(columns E–AI). A cell can be:

| Value | Meaning |
|---|---|
| empty | The radiologist is available and the model decides. |
| `G` | On-call duty (*guardia*) that day. The following day is post-call rest for the radiologists who have it (column `DORMIDA` of `Facultativos`). |
| `RJ` | Reduced working time, committee, teaching... Not available. |
| `P` | Leave. Not available. |
| `SG` | Post-call rest coming from the previous month (only needed on day 1). |
| `E` | Exception: the radiologist is excluded from the model that day and is assigned by hand afterwards. |
| a service acronym, e.g. `URG` | Fixed assignment: the radiologist must be assigned to that service. |
| `G_<service>`, e.g. `G_URG` | Fixed assignment to the service during the day and on-call duty at night. |
| `G_RJ` | Not available during the day and on-call duty at night. |

Column D shows the service of which the radiologist is holder. Columns AJ–AL count on-call duties, reduced days
and leave days. Rows 52–54 compare the on-call duties assigned each day with those required.

### `Facultativos` (staff)

One row per radiologist (rows 4–43): identifier, pseudonym, working time as a fraction of full time (`JORNADA`),
management time (`GESTIÓN`), non-clinical activity, type of on-call duty (`GUARDIAS`: `PF` on site, `LOC` on
call from home, `NO`), post-call rest (`DORMIDA`), committees, preferred and assignable shift (`M` morning,
`T` afternoon, `M/T` both), and the services of which the radiologist is holder (`TITULAR`) or first, second
or third substitute (`SUPLENTE 1–3`). The SolverStudio model is attached to this sheet.

### `Servicios` (services and calendar)

- `O4` and `O5`: month and year. All dates of the workbook are computed from these two cells.
- Row 13: holiday flags (1 = holiday).
- Rows 16–50: one row per service, with its acronym, priority (0 = mandatory, ..., 6; the legend is in `F5:G11`),
  shift and number of radiologists required.
- `G16:AK50`: demand of each service on each day (0 = closed). By default a formula closes every service on
  weekends and holidays and opens `CONTRASTADA` only on Thursdays. A service is closed on a particular day by
  typing 0 in its cell.

### `Idoneidad` (suitability)

Matrix radiologist × service (`D9:AL48`): empty or 0 = cannot be assigned, 1 = improvable, 2 = good,
3 = perfect.

### `Fijos_cod` (hidden)

Translates the text of `Especificaciones` into the numbers read by the model: the service identifier for a
fixed assignment, 100 for `G`, 100 + service identifier for `G_<service>`, 150 for `G_RJ`, 200 for `RJ` and 300
for `P`, `E` and `SG`. It also contains the dates and day types, the holder and substitute services as
identifiers, and the mark of the radiologists of the agreement with another hospital (`ALMANSA`).

### `Solucion` (hidden)

Where SolverStudio writes the result: the identifier of the service assigned to each radiologist on each day
(`E7:AI46`, 0 = none), the two components of the objective function (`A4:B4`) and the warnings (`AO6:AO65`).

### `Sol_Facultativo`, `Sol_Servicio`, `Sol_Dia` (output views)

The same solution by radiologist (service of each day), by service (radiologist of each day) and by day.
In `Sol_Facultativo`, grey cells are post-call rest, blue cells are leave or reduced time, yellow cells are
exceptions (`E`), and orange cells are radiologists who are available but have no service, who can be assigned
by hand as support. Weekends and holidays are marked in red in the header.

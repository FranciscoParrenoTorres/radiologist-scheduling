# Guardias decididas por el modelo, con las mismas cuotas que las reales

Código: `radplan/guardias.py`, `exp_guardias.py` y `exp_guardias_cambios.py`. No se ha tocado `modelo.py` ni el manuscrito.

## Qué cambia respecto a la versión con pesos de equidad

En los nueve meses reales el reparto de guardias no es proporcional a la jornada: en nueve meses hay radiólogos con
0, 3, 18 o 46 guardias, y uno al 60 % hace 44 mientras otro a jornada completa hace 23. La comisión no busca igualar,
así que el término de equidad con pesos (10, 10, 3) cambiaba el número de guardias de cada persona.

La versión nueva deja a cada radiólogo **exactamente las mismas guardias, totales y de fin de semana o festivo**, que en
el calendario real, y el modelo solo elige los días. Se añaden las reglas que cumplen los datos reales: el saliente no
cae en un día de permiso o reducción (0 casos en nueve meses), como mucho 3 guardias en 7 días (máximo real) y nunca
en días seguidos. No hay pesos que ajustar: la función objetivo es la del modelo base.

Sin los términos max–min de equidad, el modelo deja de ser difícil: **se resuelve hasta el óptimo en todos los meses
reales y semisintéticos en 1,2 segundos como máximo**.

## Meses reales (8 meses, sin septiembre)

| | Guardias reales | Modelo, mismas cuotas | Modelo, solo cuota total |
|---|---|---|---|
| Puestos-día cubiertos | 3438 | 3441 | 3441 |
| Idoneidad 3 | 2848 (82,8 %) | 2996 (87,1 %) | 3018 (87,7 %) |
| Idoneidad 1 | 138 | 82 | 67 |
| Obligatorios cubiertos sin idoneidad | 2 | 0 | 0 |
| Guardias movidas de día | – | 381 de 484 | 392 de 484 |
| Estado | óptimo | óptimo | óptimo |

La cobertura no cambia. Lo que se gana son 148 asignaciones más con idoneidad perfecta, sin cambiar las guardias de nadie.

### Cuántas guardias hay que mover

| Guardias movidas por mes (máximo) | 2 | 4 | 10 | 20 | 30 | sin límite |
|---|---|---|---|---|---|---|
| Asignaciones con idoneidad 3 ganadas (8 meses) | +33 | +47 | +77 | +125 | +145 | +148 |

Con 10 guardias movidas al mes (de unas 60) se obtiene la mitad de la mejora; con 20, el 84 %.

## Semisintéticas (36 meses; la referencia es la rueda del generador)

| Presión | Cubiertos ref. → modelo | Idoneidad 3 ref. → modelo | Obligatorios sin idoneidad |
|---|---|---|---|
| Baja | 5611 → 5628 | 84,6 % → 88,2 % | 1 → 0 |
| Media | 5289 → 5301 | 84,0 % → 88,1 % | 1 → 0 |
| Alta | 3983 → 3983 | 77,4 % → 80,4 % | 36 → 21 |

## Sintéticas (idoneidad 3, referencia → modelo, y tiempo máximo en segundos)

| Radiólogos | Idoneidad 3 | 4 semanas | 8 semanas | 13 semanas |
|---|---|---|---|---|
| 20 | 90,0 % → 90,5 % | 0,2 | 0,7 | 1,0 |
| 31 | 89,1 % → 91,5 % | 0,6 | 1,0 | 3,0 |
| 45 | 85,8 % → 90,0 % | 2,9 | 3,1 | 6,9 |
| 60 | 83,8 % → 88,2 % | 1,5 | 7,2 | 11,3 |
| 90 | 90,4 % → 94,2 % | 6,2 | 15,8 | 64,5 |
| 120 | 93,9 % → 96,7 % | 7,7 | 58,2 | 90,4 |
| 180 | – | 94,6 | 155 (2 de 3) | no ejecutadas |
| 240 | – | 84,5 | no ejecutadas | no ejecutadas |

62 de las 63 ejecutadas llegan al óptimo (HiGHS, 2 hilos, límite de 150 s). La excepción es `sint_R180_W08_media_s0`,
que se queda en el límite con una solución mala. Faltan 9: 180 radiólogos con 13 semanas y 240 con 8 y 13.

## Comprobaciones

- 0 violaciones en el comprobador en las 242 soluciones óptimas.
- En todas, cada radiólogo tiene las mismas guardias totales y de fin de semana que en la referencia, cada día tiene
  el mismo número de guardias y no hay más solapes de saliente que en la referencia.
- El valor de la referencia coincide con `reales.csv` (config `base`), y el del modelo nunca es peor que el de la referencia.

## Qué habría que cambiar en el manuscrito

1. Sección de extensiones: sustituir las restricciones de equidad y los pesos por las cuotas
   `sum_d y_rd = n_r` y `sum_{d en D^W} y_rd = n^W_r`, la prohibición del solape y el máximo de 3 en 7 días.
2. Rendimiento: ya no es cierto que «HiGHS no prueba la optimalidad en ninguna instancia». Era por los términos de equidad.
3. Tabla de guardias: usar la tabla de arriba y añadir la curva de guardias movidas.
4. Los salientes en día laborable no cambian (393 en las dos versiones), porque el número de guardias de cada día es el mismo.

## Pendiente de confirmar con el servicio

- Si el número de guardias de cada radiólogo es voluntario o acordado (es lo que supone este diseño).
- La regla de «no coincidir dos de la misma sección»: no se puede deducir de los datos (111 de las 171 parejas posibles
  coinciden alguna vez y ninguna pareja frecuente deja de coincidir).

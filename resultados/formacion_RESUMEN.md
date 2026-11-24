# Formación: qué mejoras de idoneidad abrirían más servicios

Código: `radplan/formacion.py` (modelo) y `exp_formacion.py` (experimentos). Una mejora sube a 2 la idoneidad de un par
facultativo–servicio que hoy vale 0 o 1. El modelo elige k mejoras comunes a varios meses; después cada mes se resuelve
con el modelo normal (config `base`) y se comprueba con `comprobar.py`. 0 violaciones en las 2 223 soluciones.

Ficheros: `formacion_seleccion.csv` (mejoras elegidas), `formacion_eval.csv` (evaluación en los 9 meses reales y las
36 semisintéticas), `formacion_sinteticas.csv` (24 sintéticas de 8 semanas: se elige en las semanas 1–4, se evalúa en las 5–8).

## Cuánto se puede ganar (formación ilimitada: todos los 0 y 1 pasan a 2)

| Conjunto | Demanda | Cubiertos | Cerrados | Recuperables con formación |
|---|---|---|---|---|
| Reales enero–mayo | 2520 | 2330 | 190 | 14 (7 %) |
| Reales junio–septiembre | 1895 | 1598 | 297 | 24 (8 %) |
| Semi, presión baja (12 meses) | 6326 | 5611 | 715 | 43 (6 %) |
| Semi, presión media | 6326 | 5289 | 1037 | 23 (2 %) |
| Semi, presión alta | 6326 | 3983 | 2343 | 2 (0,1 %) |
| Sintéticas, semanas 5–8 (24 inst.) | 36884 | 31003 | 5881 | 83 (1,4 %) |

Subir solo los 1 a 2 no abre ningún servicio en ningún conjunto.

## Mejoras elegidas con enero–mayo (0/1→2)

| k | Mejoras | Ene–may | Jun–sep | Semi (36) | Prioridad 2 ene–may | Asign. con idoneidad 1 ene–may |
|---|---|---|---|---|---|---|
| 0 | – | 2330 | 1598 | 14883 | 145/179 | 68 |
| 1 | R14→VAS.3 | +9 | +3 | +32 | 169 | 62 |
| 2 | + R28→NRI-2 | +13 | +3 | +40 | 169 | 63 |
| 5 | R14→MAMA T, R14→VAS.3, R26→NRI-2, R28→ECO2 HPS, R28→URG | +13 | +5 | +46 | 172 | 32 |
| 10 | (ver csv) | +13 | +3 | +46 | 175 | 25 |
| todas | 567 pares | +14 | +24 | +68 | 179 | 0 |

## Dependencia del calendario

- Eligiendo con junio–septiembre (k=10) se recuperan los 24 de esos meses, pero solo 3 de enero–mayo.
- Eligiendo con los 9 meses, k=3: R14→VAS.3, R19→URG, R31→RM M. Da +9 en ene–may, +3 en jun–sep y elimina los 2
  servicio-día obligatorios de agosto cubiertos sin idoneidad.
- Eligiendo con 12 semisintéticas (presión media), k=5: +3 en ene–may y +6 en jun–sep.

## Sintéticas (20 a 240 facultativos, k = 15 % de la plantilla)

- Semanas 1–4 (donde se elige): +104 de 109 posibles. Semanas 5–8: +64 de 83 posibles.
- Asignaciones con idoneidad 1 en las semanas 5–8: de 343 a 168.
- El modelo de selección se resuelve a optimalidad en todas (HiGHS, 2 hilos): 0,7 s con 31 facultativos, 13 s con 120
  y 43–66 s con 240 (660 000 variables).

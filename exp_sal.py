import sys, glob, csv
from dataclasses import replace
from radplan import Instancia, Config, construir, resolver, evaluar
cfg=Config(cobertura="blanda", guardias="modelo", w_saliente=1000.0)
out=open('resultados/guardias_sin_solape.csv','a')
for p in sys.argv[1:]:
    I=Instancia.cargar(p); r=resolver(construir(I,cfg),'highs',tl=60)
    ev=evaluar(I,r['sol'],cfg); k=ev['kpi']
    G=r['sol']['guardia']; solape=sum(1 for f in range(I.nF) for t in range(I.nD) if G[f][t] and I.destino_saliente(t)<I.nD and I.laborable[I.destino_saliente(t)] and I.estado[f][I.destino_saliente(t)]!='')
    print(I.nombre,r['estado'],round(r['gap'] or -1,4),k['servicios'],k['SG'],k['idoneidad3'],solape,ev['n_violaciones'],sep=',',file=out,flush=True)

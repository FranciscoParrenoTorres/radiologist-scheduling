"""radplan: planificación mensual de radiólogos (instancias, modelo, comprobador, generador y experimentos)."""
from .instancia import Instancia, NIVELES
from .modelo import Config, construir, resolver
from .comprobar import evaluar

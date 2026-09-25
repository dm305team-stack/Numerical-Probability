"""La matriz del juego como DATO, no incrustada en el codigo.

Decision de diseno: el usuario pidio Powerball ahora y Mega Millions despues sin
reescribir el motor. Todo el motor recibe una Matriz; ninguna funcion asume 69
ni 26.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Matriz:
    clave: str
    nombre: str
    principales: int       # cuantas bolas principales se eligen
    max_principal: int     # rango 1..max_principal
    max_extra: int         # rango 1..max_extra para la bola extra
    nombre_extra: str
    dias_sorteo: tuple     # 0=lunes .. 6=domingo

    @property
    def combinaciones(self):
        from math import comb
        return comb(self.max_principal, self.principales) * self.max_extra


POWERBALL = Matriz(
    clave="powerball",
    nombre="Powerball",
    principales=5,
    max_principal=69,
    max_extra=26,
    nombre_extra="Powerball",
    dias_sorteo=(0, 2, 5),  # lunes, miercoles, sabado
)

# Preparada, sin datos historicos todavia. La ingesta oficial debe llenarla
# antes de ofrecerla en la interfaz.
MEGA_MILLIONS = Matriz(
    clave="mega-millions",
    nombre="Mega Millions",
    principales=5,
    max_principal=70,
    max_extra=25,
    nombre_extra="Mega Ball",
    dias_sorteo=(1, 4),  # martes, viernes
)

MATRICES = {m.clave: m for m in (POWERBALL, MEGA_MILLIONS)}

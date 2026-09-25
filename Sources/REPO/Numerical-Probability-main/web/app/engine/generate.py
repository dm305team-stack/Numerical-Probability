"""Generacion de boletos. El orden de consumo del RNG es CONTRACTUAL.

tests/test_golden.py comprueba que, sin restricciones, este modulo reproduce
exactamente los boletos del baseline medido. Cualquier cambio en el orden de
las llamadas a rng -- incluida la posicion del rng.random() dentro de _acepta --
rompe esa reproducibilidad. Si tocas algo aqui, corre los tests.

Para que el golden se mantenga, la ruta SIN restricciones usa exactamente la
misma poblacion (1..max) y los mismos pesos que el baseline. Las restricciones
de incluir/excluir abren una ruta distinta a proposito: consumen el RNG de otra
forma y por eso no comparten golden.
"""
import random
import time

EXPONENTE_PESO = 3          # los pesos son score**3, como en el baseline
PROB_DESCARTE_CONSECUTIVO = 0.72
MIN_DECENAS = 4
MAX_SOLAPAMIENTO = 1        # numeros compartidos entre dos boletos cualesquiera
INTENTOS_MAXIMOS = 500000
PRESUPUESTO_S = 0.75   # tope de CPU por peticion: sin esto son 3,6 s y es un vector de DoS


class NoConverge(RuntimeError):
    """Las restricciones pedidas no dejan sitio para tantos boletos."""


def generar(
    score,
    score_extra,
    matriz,
    perfil_hist,
    semilla,
    cuantos=5,
    incluir=(),
    excluir=(),
    incluir_en=1,
    presupuesto_s=PRESUPUESTO_S,
):
    """Genera `cuantos` boletos deterministas a partir de `semilla`.

    incluir      numeros que deben aparecer
    incluir_en   en cuantos boletos debe aparecer COMO MINIMO cada numero de
                 `incluir`; puede salir en mas si el azar lo elige
    excluir      numeros prohibidos, tanto en principales como en la bola extra
    """
    incluir = sorted(set(incluir))
    excluir = set(excluir)
    choque = set(incluir) & excluir
    if choque:
        raise NoConverge(f"pides incluir y excluir a la vez: {sorted(choque)}")
    if len(incluir) > cuantos * matriz.principales:
        raise NoConverge("pides incluir mas numeros de los que caben")

    rng = random.Random(semilla)
    q1, q3 = perfil_hist["suma_q1"], perfil_hist["suma_q3"]
    umbral_bajos = perfil_hist["umbral_bajos"]

    poblacion = [n for n in range(1, matriz.max_principal + 1) if n not in excluir]
    pesos = [score[n] ** EXPONENTE_PESO for n in poblacion]
    poblacion_e = [p for p in range(1, matriz.max_extra + 1) if p not in excluir]
    pesos_e = [score_extra[p] ** EXPONENTE_PESO for p in poblacion_e]
    if not poblacion_e:
        raise NoConverge("has excluido todas las bolas extra posibles")

    # a que boleto le toca cada numero forzado: reparto ciclico y estable
    forzados = {}
    ranura = 0
    for numero in incluir:
        for _ in range(min(incluir_en, cuantos)):
            forzados.setdefault(ranura % cuantos, set()).add(numero)
            ranura += 1

    boletos, extras_usadas, numeros_usados = [], set(), set()
    intentos = 0
    limite = time.monotonic() + presupuesto_s
    while len(boletos) < cuantos and intentos < INTENTOS_MAXIMOS:
        intentos += 1
        # el reloj se mira cada 512 vueltas: mirarlo siempre cuesta mas que generar
        if not intentos & 511 and time.monotonic() > limite:
            break
        obligatorios = forzados.get(len(boletos), set())
        elegidos = set(obligatorios)
        while len(elegidos) < matriz.principales:
            elegidos.add(rng.choices(poblacion, weights=pesos)[0])
        principales = sorted(elegidos)
        if len(principales) != matriz.principales:
            # solo puede pasar si los forzados de un boleto pasan de las bolas
            # que caben. Un boleto de 6 bolas no se puede ni comprar.
            raise NoConverge(
                f"pides {len(principales)} números forzados en un mismo boleto "
                f"y sólo caben {matriz.principales}"
            )
        extra = rng.choices(poblacion_e, weights=pesos_e)[0]
        if _acepta(
            principales, extra, rng, q1, q3, umbral_bajos, matriz,
            extras_usadas, numeros_usados, obligatorios,
        ):
            boletos.append((principales, extra))
            extras_usadas.add(extra)
            numeros_usados |= set(principales)

    if len(boletos) < cuantos:
        raise NoConverge(
            f"solo salieron {len(boletos)} de {cuantos} boletos: las restricciones "
            f"no dejan sitio para tantos. Los boletos no pueden compartir más de "
            f"{MAX_SOLAPAMIENTO} número entre sí, así que repetir varios números "
            f"fijos en varios boletos choca con esa regla. Sin restricciones, el "
            f"máximo son 14."
        )
    return boletos, intentos


def _acepta(
    principales, extra, rng, q1, q3, umbral_bajos, matriz,
    extras_usadas, numeros_usados, obligatorios,
):
    """Filtros estructurales. ORDEN CONTRACTUAL: el rng.random() del filtro de
    consecutivos solo se consume si los filtros anteriores han pasado."""
    if not q1 <= sum(principales) <= q3:
        return False
    impares = sum(1 for n in principales if n % 2)
    if impares not in (2, 3):
        return False
    bajos = sum(1 for n in principales if n <= umbral_bajos)
    if bajos not in (2, 3):
        return False
    if len(set((n - 1) // 10 for n in principales)) < MIN_DECENAS:
        return False
    hay_consecutivos = any(
        principales[i + 1] - principales[i] == 1
        for i in range(matriz.principales - 1)
    )
    if hay_consecutivos and rng.random() < PROB_DESCARTE_CONSECUTIVO:
        return False
    if extra in extras_usadas:
        return False
    # El solapamiento se cuenta ENTERO, incluidos los numeros forzados.
    # Antes se restaban los obligatorios "porque el usuario los pidio", y eso
    # permitia entregar dos boletos que compartian 3 numeros, rompiendo el
    # contrato que el propio motor promete. Si pedir un numero en varios
    # boletos choca con el limite de solape, se avisa; no se incumple.
    compartidos = numeros_usados & set(principales)
    if len(compartidos) > MAX_SOLAPAMIENTO:
        return False
    return True

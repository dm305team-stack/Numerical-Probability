"""Pruebas estadisticas. PORTADAS VERBATIM de Analysis/baseline_analysis.py.

No toques la aritmetica de este modulo sin correr tests/test_golden.py. El
chi2_sf esta implementado a mano con serie y fraccion continua porque el
proyecto no depende de scipy; sus constantes de corte (1e-14, 1e-300) y su
numero de iteraciones son parte del resultado medido.
"""
import collections
import math
import random


def chi2(counter, k, total):
    """Chi-cuadrado de bondad de ajuste contra la uniforme sobre 1..k."""
    esperado = total / k
    return sum((counter.get(i, 0) - esperado) ** 2 / esperado for i in range(1, k + 1))


def chi2_sf(x, df):
    """Funcion de supervivencia de chi-cuadrado (p-valor). Verbatim del baseline."""
    if x <= 0:
        return 1.0
    a, xx = df / 2.0, x / 2.0
    if xx < a + 1:
        s = 1.0 / a
        t = s
        n = 0
        while True:
            n += 1
            t *= xx / (a + n)
            s += t
            if abs(t) < abs(s) * 1e-14 or n > 10000:
                break
        return 1.0 - s * math.exp(-xx + a * math.log(xx) - math.lgamma(a))
    tiny = 1e-300
    b = xx + 1 - a
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, 10000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        de = d * c
        h *= de
        if abs(de - 1) < 1e-14:
            break
    return math.exp(-xx + a * math.log(xx) - math.lgamma(a)) * h


def runs_test(sums):
    """Test de rachas sobre las sumas, contra su mediana. Devuelve (runs, esperado, z)."""
    n = len(sums)
    mediana = sorted(sums)[n // 2]
    seq = [1 if s > mediana else 0 for s in sums if s != mediana]
    runs = 1 + sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1])
    n1 = sum(seq)
    n0 = len(seq) - n1
    mu = 2 * n1 * n0 / (n1 + n0) + 1
    sd = math.sqrt(
        2 * n1 * n0 * (2 * n1 * n0 - n1 - n0) / ((n1 + n0) ** 2 * (n1 + n0 - 1))
    )
    return runs, mu, (runs - mu) / sd


def _x2_transiciones(seq):
    t2 = collections.Counter(zip(seq, seq[1:]))
    r2 = collections.Counter()
    c2 = collections.Counter()
    for (a, b), c in t2.items():
        r2[a] += c
        c2[b] += c
    tt = sum(t2.values())
    return sum(
        (t2.get((a, b), 0) - r2[a] * c2[b] / tt) ** 2 / (r2[a] * c2[b] / tt)
        for a in r2
        for b in c2
    )


def markov_permutacion(draws, permutaciones=20000, semilla=2):
    """Independencia serial de la decena del numero mas bajo.

    La aproximacion chi2 NO aplica aqui: con los estados sin colapsar hay 17
    celdas con esperado < 5 y da p ~ 0,0000, un falso positivo. Por eso se
    colapsan los estados >= 3 y se contrasta contra permutaciones del orden
    temporal. Esto ya se descubrio y corrigio en el baseline; no lo "simplifiques"
    de vuelta al chi2 directo.
    """
    estados = [min(3, min(m) // 10) for m, _ in draws]
    obs = _x2_transiciones(estados)
    rng = random.Random(semilla)
    nulo = [
        _x2_transiciones(rng.sample(estados, len(estados)))
        for _ in range(permutaciones)
    ]
    p = sum(1 for v in nulo if v >= obs) / permutaciones
    return obs, p

#!/usr/bin/env python3
"""Numerical Probability - baseline local (sin API), acotado a la matriz vigente
5/69 + PB 1/26 y con el orden temporal corregido: Base-Secuence.pdf viene
ordenado del sorteo MAS NUEVO al MAS VIEJO.

Sirve de referencia para contrastar lo que produzca la app (Opus + code
execution). Uso:

    python3 Analysis/baseline_analysis.py

Requiere `pdftotext` (poppler). Reproducible: semilla fija 20260727.
"""
import os, re, math, random, collections, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PDF = os.path.join(HERE, "..", "Knowledge", "Base-Secuence.pdf")
TXT = os.path.join(tempfile.gettempdir(), "np_base.txt")
if not os.path.exists(TXT):
    subprocess.run(["pdftotext", "-layout", PDF, TXT], check=True)

rows = []
for l in open(TXT):
    n = [int(x) for x in re.findall(r"\d+", l)]
    if len(n) == 6: rows.append(n)

# Frontera de cambio de matriz (oct-2015): la primera fila con PB>26 marca el
# inicio de la era antigua 5/59 + PB 1/35. Se descarta todo lo anterior a ella.
CUT = next((i for i, r in enumerate(rows) if r[5] > 26), len(rows))
modern = rows[:CUT]
# el archivo esta en orden descendente por fecha -> invertir a cronologico
modern = modern[::-1]
draws = [(sorted(r[:5]), r[5]) for r in modern
         if all(1 <= x <= 69 for x in r[:5]) and 1 <= r[5] <= 26 and len(set(r[:5])) == 5]
N = len(draws)
print(f"=== 1. DATOS ===\nSorteos en matriz vigente 5/69 + PB 1/26: {N}")
print(f"Descartados por cambio de matriz (era 5/59 + PB 1/35): {len(rows) - CUT}\n")

fmain = collections.Counter(); fpb = collections.Counter()
for m, p in draws: fmain.update(m); fpb[p] += 1

def chi2(c, k, tot):
    e = tot / k
    return sum((c.get(i, 0) - e) ** 2 / e for i in range(1, k + 1))

def chi2_sf(x, df):
    if x <= 0: return 1.0
    a, xx = df / 2.0, x / 2.0
    if xx < a + 1:
        s = 1.0 / a; t = s; n = 0
        while True:
            n += 1; t *= xx / (a + n); s += t
            if abs(t) < abs(s) * 1e-14 or n > 10000: break
        return 1.0 - s * math.exp(-xx + a * math.log(xx) - math.lgamma(a))
    tiny = 1e-300; b = xx + 1 - a; c = 1 / tiny; d = 1 / b; h = d
    for i in range(1, 10000):
        an = -i * (i - a); b += 2
        d = an * d + b; d = tiny if abs(d) < tiny else d
        c = b + an / c; c = tiny if abs(c) < tiny else c
        d = 1 / d; de = d * c; h *= de
        if abs(de - 1) < 1e-14: break
    return math.exp(-xx + a * math.log(xx) - math.lgamma(a)) * h

x2m, x2p = chi2(fmain, 69, N * 5), chi2(fpb, 26, N)
pm, pp = chi2_sf(x2m, 68), chi2_sf(x2p, 25)
print("=== 2. ALEATORIEDAD vs DETERMINISMO ===")
print(f"  Bolas principales : X2 = {x2m:6.2f}  df=68  p = {pm:.4f}")
print(f"  Powerball         : X2 = {x2p:6.2f}  df=25  p = {pp:.4f}")
print(f"  Veredicto: {'NO se rechaza' if pm > .05 else 'SE RECHAZA'} la uniformidad en principales;"
      f" {'NO se rechaza' if pp > .05 else 'SE RECHAZA'} en Powerball.")

sums = [sum(m) for m, _ in draws]
med = sorted(sums)[len(sums) // 2]
seq = [1 if s > med else 0 for s in sums if s != med]
runs = 1 + sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1])
n1 = sum(seq); n0 = len(seq) - n1
mu = 2 * n1 * n0 / (n1 + n0) + 1
sd = math.sqrt(2 * n1 * n0 * (2 * n1 * n0 - n1 - n0) / ((n1 + n0) ** 2 * (n1 + n0 - 1)))
print(f"  Runs test (sumas) : runs={runs} esp={mu:.1f} z={(runs-mu)/sd:+.3f} -> sin memoria serial")

# Markov de primer orden sobre la decena del numero mas bajo (test de independencia)
tr = collections.Counter()
st = [min(m) // 10 for m, _ in draws]
for a, b in zip(st, st[1:]): tr[(a, b)] += 1
rowt = collections.Counter(a for a, _ in tr.elements() if True)
rowsum = collections.Counter()
colsum = collections.Counter()
for (a, b), c in tr.items(): rowsum[a] += c; colsum[b] += c
tot = sum(tr.values()); x2mk = 0.0; cells = 0
for a in rowsum:
    for b in colsum:
        e = rowsum[a] * colsum[b] / tot
        if e > 0: x2mk += (tr.get((a, b), 0) - e) ** 2 / e; cells += 1
dfmk = (len(rowsum) - 1) * (len(colsum) - 1)
sparse = sum(1 for a in rowsum for b in colsum if rowsum[a] * colsum[b] / tot < 5)
print(f"  Markov orden-1 (decena del minimo): X2={x2mk:.1f} df={dfmk} "
      f"p={chi2_sf(x2mk, dfmk):.4f}  <-- NO usar: {sparse} celdas con esperado<5")

# La aproximacion chi2 no aplica con celdas tan vacias. Se colapsan los estados
# raros (>=3) y se contrasta contra una permutacion del orden temporal.
stc = [min(3, s) for s in st]
def _x2(seq):
    t2 = collections.Counter(zip(seq, seq[1:])); r2 = collections.Counter(); c2 = collections.Counter()
    for (a, b), c in t2.items(): r2[a] += c; c2[b] += c
    tt = sum(t2.values())
    return sum((t2.get((a, b), 0) - r2[a]*c2[b]/tt) ** 2 / (r2[a]*c2[b]/tt) for a in r2 for b in c2)
_obs = _x2(stc); _rng = random.Random(2)
_null = [_x2(_rng.sample(stc, len(stc))) for _ in range(20000)]
print(f"  Markov, estados colapsados + permutacion (20k): X2={_obs:.2f} "
      f"p={sum(1 for v in _null if v >= _obs)/20000:.4f} -> sin dependencia serial")

print("\n=== 3. ESTRUCTURA (perfiles empiricos que SI son estables) ===")
odd = sum(1 for m, _ in draws for n in m if n % 2)
lo = sum(1 for m, _ in draws for n in m if n <= 35)
print(f"  impares {100*odd/(N*5):.1f}%   bajos<=35 {100*lo/(N*5):.1f}%   (uniforme = 50.7%)")
oddist = collections.Counter(sum(1 for n in m if n % 2) for m, _ in draws)
print("  reparto impar/par por sorteo:", " ".join(f"{k}i:{100*oddist[k]/N:.1f}%" for k in range(6)))
q1, q3 = sorted(sums)[N // 4], sorted(sums)[3 * N // 4]
print(f"  suma: mediana {med}, rango intercuartil {q1}-{q3} (50% de los sorteos)")
consec = sum(1 for m, _ in draws if any(m[i+1]-m[i] == 1 for i in range(4)))
print(f"  al menos un par consecutivo: {100*consec/N:.1f}%")
decs = collections.Counter(len(set((n-1)//10 for n in m)) for m, _ in draws)
print("  decenas distintas por sorteo:", " ".join(f"{k}:{100*decs[k]/N:.1f}%" for k in sorted(decs)))

# ---- 4. Ranking: frecuencia + retraso, ahora con el tiempo bien orientado ----
last = {}
for i, (m, _) in enumerate(draws):
    for n in m: last[n] = i
gap = {n: N - 1 - last.get(n, -1) for n in range(1, 70)}
mg = sum(gap.values()) / 69
em = N * 5 / 69
score = {n: 0.55 * (fmain.get(n, 0) / em) + 0.45 * min(gap[n] / mg, 2.5) for n in range(1, 70)}

lastp = {}
for i, (_, p) in enumerate(draws): lastp[p] = i
gp = {p: N - 1 - lastp.get(p, -1) for p in range(1, 27)}
mgp = sum(gp.values()) / 26
ep = N / 26
pbs = {p: 0.55 * (fpb.get(p, 0) / ep) + 0.45 * min(gp[p] / mgp, 2.5) for p in range(1, 27)}

print("\n=== 4. RANKING (55% frecuencia historica + 45% retraso) ===")
top = sorted(score, key=score.get, reverse=True)
print("  principales top-14:", " ".join(f"{n:02d}({score[n]:.2f})" for n in top[:14]))
print("  mas frecuentes    :", " ".join(f"{n:02d}x{fmain[n]}" for n, _ in fmain.most_common(8)))
tp = sorted(pbs, key=pbs.get, reverse=True)
print("  powerball top-6   :", " ".join(f"{p:02d}({pbs[p]:.2f})" for p in tp[:6]))

# ---- 5. Generacion ----
rng = random.Random(20260727)
W = [score[n] ** 3 for n in range(1, 70)]
PW = [pbs[p] ** 3 for p in range(1, 27)]

def ok(m, p, upb, un):
    if not (q1 <= sum(m) <= q3): return False
    if sum(1 for n in m if n % 2) not in (2, 3): return False
    if sum(1 for n in m if n <= 35) not in (2, 3): return False
    if len(set((n - 1) // 10 for n in m)) < 4: return False
    if any(m[i+1]-m[i] == 1 for i in range(4)) and rng.random() < .72: return False
    if p in upb: return False
    if len(un & set(m)) > 1: return False
    return True

seqs, upb, un = [], set(), set()
t = 0
while len(seqs) < 5 and t < 500000:
    t += 1
    pick = set()
    while len(pick) < 5: pick.add(rng.choices(range(1, 70), weights=W)[0])
    m = sorted(pick); p = rng.choices(range(1, 27), weights=PW)[0]
    if ok(m, p, upb, un):
        seqs.append((m, p)); upb.add(p); un |= set(m)

C = math.comb(69, 5) * 26
print(f"\n=== 5. GENERACION ===\n  intentos: {t}   espacio muestral C(69,5)x26 = {C:,}")

mc = 300000; hit = collections.Counter(); mr = random.Random(7)
for _ in range(mc):
    d = set(mr.sample(range(1, 70), 5)); dp = mr.randrange(1, 27)
    for i, (m, p) in enumerate(seqs):
        h = len(d & set(m))
        if dp == p or h >= 3: hit[i] += 1
print(f"\n=== 6. MONTE CARLO ({mc:,} sorteos) — tasa de premio de cualquier nivel ===")
for i in range(5): print(f"  boleto {i+1}: {100*hit[i]/mc:.3f}%   (teorico 3.90%)")

print("\n<final_sequences>")
for i, (m, p) in enumerate(seqs, 1):
    print(f"{i}. " + " ".join(f"{n:02d}" for n in m) + f" {p:02d} | probability: {100/C:.10f}%")
print("</final_sequences>")

print("\n=== PERFIL DE CADA BOLETO ===")
for i, (m, p) in enumerate(seqs, 1):
    print(f"  {i}: suma {sum(m):3d} | impares {sum(1 for n in m if n%2)}/5 | "
          f"bajos {sum(1 for n in m if n<=35)}/5 | decenas {len(set((n-1)//10 for n in m))}")
print(f"  cobertura: {len(un)}/25 numeros distintos, {len(upb)}/5 powerballs distintos")

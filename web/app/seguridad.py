"""Limites de entrada, acceso y limitacion de peticiones.

Modelo de amenaza de esta app:
  - Es privada tras una UNICA clave compartida, en un dominio publico. Quien
    encuentre el dominio puede aporrear el login.
  - Cada peticion aceptada puede disparar DOS llamadas de pago a OpenRouter.
    El atacante no busca datos: busca gastarte los creditos.
  - El texto del usuario entra en el prompt de un modelo. Es superficie de
    inyeccion de instrucciones.
  - La generacion es cara en CPU si las restricciones aprietan. Medido: hasta
    3,6 s por peticion antes de este modulo.
Todo lo de aqui falla CERRADO: ante la duda, se rechaza.
"""
import hashlib
import hmac
import os
import re
import secrets
import time
from collections import defaultdict, deque

import entorno

# web/.env se carga ANTES de leer nada de os.environ: las variables de abajo
# se resuelven en tiempo de import y sin esto llegarian vacias.
entorno.cargar()

# ------------------------------------------------------------- limites duros
MAX_PETICION = 400        # una peticion de loteria no necesita mas
MAX_SEMILLA_DIGITOS = 19  # cabe en 64 bits con holgura
MAX_CLAVE = 256
MAX_LISTA = 10            # cuantos numeros puede incluir o excluir a la vez
MAX_CUERPO = 16 * 1024    # bytes de cuerpo admitidos: un boleto no necesita mas
MAX_CUBOS = 20000         # IPs distintas que recuerda el limitador antes de podar
MAX_BOLETOS = 14          # techo REAL medido bajo la regla de solape <= 1
PRESUPUESTO_CPU = 0.75    # segundos de generacion por peticion

MODO_LOCAL = os.environ.get("LOCAL") == "1"
APP_KEY = os.environ.get("APP_KEY") or ""


class EntradaInvalida(ValueError):
    """Lo que ve el usuario. Nunca lleva detalle interno."""


class ArranqueInseguro(RuntimeError):
    pass


def comprobar_arranque():
    """Falla CERRADO: desplegada sin clave no arranca.

    El fallo que esto evita es el silencioso: APP_KEY vacia por una variable de
    entorno mal puesta deja la app abierta sin que nada lo diga.
    """
    if MODO_LOCAL:
        return "local"
    if len(APP_KEY) < 16:
        raise ArranqueInseguro(
            "APP_KEY ausente o demasiado corta (minimo 16 caracteres). "
            "Para pruebas locales sin clave, arranca con LOCAL=1."
        )
    return "privado"


# ------------------------------------------------------------- sesion
def _secreto_servidor():
    """Secreto de firma. Si no se fija, se genera y las sesiones mueren al
    reiniciar, que es el fallo seguro."""
    s = os.environ.get("SESSION_SECRET")
    if not s:
        s = secrets.token_hex(32)
        os.environ["SESSION_SECRET"] = s
    return s.encode()


def emitir_sesion():
    """Valor de cookie. NO deriva de APP_KEY: si la cookie se filtra, no revela
    la clave, y rotar SESSION_SECRET invalida todas las sesiones."""
    return hmac.new(_secreto_servidor(), b"auth:v1", hashlib.sha256).hexdigest()


def _iguales(a, b):
    """Comparacion en tiempo constante que NO revienta.

    hmac.compare_digest sobre str lanza TypeError si hay un solo caracter
    no-ASCII. Una cookie con una 'e' acentuada tumbaba TODAS las rutas con un
    500, sin clave y sin pasar por el limitador. Se compara en bytes.
    """
    try:
        if isinstance(a, str):
            a = a.encode("utf-8", "surrogatepass")
        if isinstance(b, str):
            b = b.encode("utf-8", "surrogatepass")
        return hmac.compare_digest(a, b)
    except (TypeError, ValueError, UnicodeError):
        return False


def sesion_valida(valor):
    if MODO_LOCAL and not APP_KEY:
        return True
    if not valor or not isinstance(valor, str):
        return False
    return _iguales(valor, emitir_sesion())


def clave_correcta(entregada):
    """Comparacion en tiempo constante: sin esto, el tiempo de respuesta filtra
    cuantos caracteres iniciales son correctos."""
    if not APP_KEY or not entregada:
        return False
    if len(entregada) > MAX_CLAVE:
        return False
    return _iguales(entregada, APP_KEY)


# ------------------------------------------------------------- limitador
class Limitador:
    """Ventana deslizante en memoria. Suficiente para un contenedor unico.

    Si algun dia hay mas de una replica hace falta almacen compartido; hoy no
    lo hay, y un limitador por proceso es mejor que ninguno.
    """

    def __init__(self, permitidas, ventana_s, castigo_s=0):
        self.permitidas = permitidas
        self.ventana = ventana_s
        self.castigo = castigo_s
        self._golpes = defaultdict(deque)
        self._bloqueados = {}

    def _ahora(self):
        return time.monotonic()

    def _podar(self, ahora):
        """Sin esto, _golpes crece para siempre: 60.000 IPs distintas medidas
        anadian 60 MB de RSS y nada las borraba salvo un login acertado."""
        if len(self._golpes) < MAX_CUBOS and len(self._bloqueados) < MAX_CUBOS:
            return
        for k in [k for k, v in self._bloqueados.items() if v <= ahora]:
            del self._bloqueados[k]
        for k in [k for k, c in self._golpes.items()
                  if not c or c[-1] < ahora - self.ventana]:
            del self._golpes[k]
        if len(self._golpes) >= MAX_CUBOS:
            # ultimo recurso: se vacia entero. Perder memoria de quien ha
            # llamado es preferible a quedarse sin memoria.
            self._golpes.clear()

    def consultar(self, clave):
        """Devuelve segundos que faltan para poder reintentar, o 0 si pasa."""
        ahora = self._ahora()
        self._podar(ahora)
        hasta = self._bloqueados.get(clave, 0)
        if hasta > ahora:
            return int(hasta - ahora) + 1
        cola = self._golpes[clave]
        while cola and cola[0] < ahora - self.ventana:
            cola.popleft()
        if len(cola) >= self.permitidas:
            if self.castigo:
                self._bloqueados[clave] = ahora + self.castigo
                return self.castigo
            return int(self.ventana - (ahora - cola[0])) + 1
        cola.append(ahora)
        return 0

    def perdonar(self, clave):
        self._golpes.pop(clave, None)
        self._bloqueados.pop(clave, None)


# login: 5 intentos por cuarto de hora y luego 15 minutos de castigo
LIMITE_LOGIN = Limitador(permitidas=5, ventana_s=900, castigo_s=900)
# generacion: 20 por minuto, que ya es mas de lo que teclea una persona
LIMITE_GENERAR = Limitador(permitidas=20, ventana_s=60)


class PresupuestoDiario:
    """Tope de llamadas de pago al modelo por dia. Al agotarse, la app sigue
    sirviendo boletos con el interprete local: se degrada, no se cae."""

    def __init__(self, tope=int(os.environ.get("TOPE_LLM_DIARIO", "300"))):
        self.tope = tope
        self._dia = None
        self._gastadas = 0

    def _hoy(self):
        return time.gmtime().tm_yday

    def hay(self):
        if self._dia != self._hoy():
            self._dia, self._gastadas = self._hoy(), 0
        return self._gastadas < self.tope

    def gastar(self, n=1):
        if self._dia != self._hoy():
            self._dia, self._gastadas = self._hoy(), 0
        self._gastadas += n

    @property
    def restantes(self):
        return max(0, self.tope - self._gastadas) if self._dia == self._hoy() else self.tope


PRESUPUESTO_LLM = PresupuestoDiario()


# IPs de los proxies en los que confiamos para leer X-Forwarded-For.
# VACIO a proposito: sin configurarlo NO se lee ninguna cabecera, porque
# creersela sin proxy delante deja que el atacante elija su propia IP y anule
# el limitador entero.
PROXIES_DE_CONFIANZA = {
    x.strip() for x in os.environ.get("PROXIES_DE_CONFIANZA", "").split(",") if x.strip()
}


def ip_de(request):
    """IP real del cliente.

    Las dos formas de equivocarse aqui, y las dos son graves:
      - Fiarse de X-Forwarded-For sin proxy -> el atacante pone la IP que
        quiera y el limitador no limita nada.
      - No leerla habiendo proxy -> todo el mundo comparte cubo, y cinco
        contrasenas malas de un desconocido dejan sin entrar a todo el equipo.
    Por eso solo se lee si el salto inmediato esta en PROXIES_DE_CONFIANZA.
    """
    directa = request.client.host if request.client else "desconocida"
    if directa in PROXIES_DE_CONFIANZA:
        reenviada = request.headers.get("x-forwarded-for", "")
        primera = reenviada.split(",")[0].strip()
        if primera:
            return primera[:64]
    return directa


# ------------------------------------------------------------- saneado
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def limpiar_peticion(texto):
    """Lo que escribe el usuario, acotado y sin caracteres de control."""
    if texto is None:
        return ""
    if not isinstance(texto, str):
        raise EntradaInvalida("petición no válida")
    if len(texto) > MAX_PETICION:
        raise EntradaInvalida(
            f"la petición no puede pasar de {MAX_PETICION} caracteres "
            f"(mandaste {len(texto)})"
        )
    return _CONTROL.sub("", texto).strip()


def limpiar_semilla(valor):
    """None si no la fija; entero acotado si la fija."""
    if valor is None:
        return None
    valor = str(valor).strip()
    if not valor:
        return None
    if len(valor) > MAX_SEMILLA_DIGITOS or not valor.isdigit():
        raise EntradaInvalida(
            f"la semilla debe ser un número de hasta {MAX_SEMILLA_DIGITOS} dígitos"
        )
    return int(valor)


CABECERAS = {
    # sin CDN ni scripts externos: todo se sirve desde el propio origen
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'; "
        "object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

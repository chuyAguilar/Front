"""Timeout de datos (F1.2) en el dashboard y la tarjeta reales (flet sin montar).

Reloj falso inyectado: el tiempo solo avanza cuando el test lo dice, y el
timer se ejerce llamando a _tick() / _vigilar() directamente.

Este archivo importa SOLO nombres que ya existían en F1.1 (SIN_DATOS va como
literal) para poder correrlo también contra el código de F1.1 (cbe51cb) y
mostrar que ahí FALLA.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

import componentes.bed_card as bed_card
import vistas.dashboard as dashboard_mod
from datos import conexion
from componentes.bed_card import AMBAR_SIN_CONEXION, GRIS_OFFLINE, VERDE_ONLINE, BedCard
from componentes.signo import Signo
from vistas.dashboard import Dashboard

SIN_DATOS = "sin_datos"
GRIS_VALOR = "#3d5a73"      # color del "--" (signo.py)


class RelojFalso:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class _LoopInmediato:
    def call_soon_threadsafe(self, fn, *args):
        fn(*args)


class _LoopDiferido:
    """Como el loop de flet visto desde el hilo de paho: encola y NO ejecuta
    hasta que el loop corre (drenar)."""

    def __init__(self):
        self.pendientes = []

    def call_soon_threadsafe(self, fn, *args):
        self.pendientes.append((fn, args))

    def drenar(self):
        while self.pendientes:
            fn, args = self.pendientes.pop(0)
            fn(*args)


class _PaginaFalsa:
    def __init__(self, loop=None):
        self.loop = loop or _LoopInmediato()
        self.tareas = []

    def run_task(self, fn, *args):
        self.tareas.append(fn)
        return object()


class DashboardDePrueba(Dashboard):
    _pagina = None

    @property
    def page(self):
        if self._pagina is None:
            self._pagina = _PaginaFalsa()
        return self._pagina

    def update(self):
        pass

    def agregar_tarjeta(self, tarjeta):
        # foto de la tarjeta en el instante en que se monta en la pantalla
        self.al_montar = {
            "punto": tarjeta.punto_estado.bgcolor,
            "etiqueta_visible": tarjeta.etiqueta_estado.visible,
            "etiqueta": tarjeta.etiqueta_estado.value,
            "fc": tarjeta.signos["fc"].valor_texto.value,
        }
        super().agregar_tarjeta(tarjeta)


def _dashboard(reloj=None):
    alertas = []
    d = DashboardDePrueba(lambda _n: None, lambda cama, hay: alertas.append((cama, hay)))
    d._reloj = reloj or RelojFalso()
    return d, alertas


def _ts(hace_s=0):
    instante = datetime.now(timezone.utc) - timedelta(seconds=hace_s)
    return instante.strftime("%Y-%m-%dT%H:%M:%SZ")


SIGNOS = {"fc": {"valor": 100}, "spo2": {"valor": 97}, "fp": {"valor": 99},
          "fr": {"valor": 20}, "temp": {"valor": 36.8}, "pni": None}
FC_FUERA = {**SIGNOS, "fc": {"valor": 30}}       # bradicardia: fuera de rango


class _PaginaDeSigno:
    def __init__(self):
        self.tareas = []

    def run_task(self, fn):
        self.tareas.append(fn)


@pytest.fixture
def pagina_de_signo(monkeypatch):
    pagina = _PaginaDeSigno()
    monkeypatch.setattr(Signo, "page", property(lambda self: pagina))
    return pagina


def _en_sin_datos(t):
    return (t.punto_estado.bgcolor != VERDE_ONLINE and t.etiqueta_estado.visible is True
            and t.etiqueta_estado.value == "Sin datos"
            and t.signos["fc"].valor_texto.value == "--")


# ---- requisito 4: la tarjeta nacida solo con vitales viejas nunca llega a verde ----

@pytest.mark.parametrize("orden", ["estado_primero", "vital_primero"])
def test_nacida_con_vitales_viejas_nunca_llega_a_verde(orden):
    # el apagón real (ADR-024 §4): el broker del edge restaura del disco el
    # 'online' y las vitales de hace horas, y el bridge los re-publica
    reloj = RelojFalso()
    d, _ = _dashboard(reloj)
    vieja = _ts(hace_s=3 * 3600)
    if orden == "estado_primero":
        d.al_enlace_edge("jetson-01", True)
        d.al_estado_cama("cama-09", "online")
        d.al_vitales("cama-09", SIGNOS, "jetson-01", vieja)
        # ya AL MONTARSE: no verde, etiqueta "Sin datos"
        assert d.al_montar["punto"] != VERDE_ONLINE
        assert d.al_montar["etiqueta_visible"] is True
        assert d.al_montar["etiqueta"] == "Sin datos"
        assert d.al_montar["fc"] == "--"
    else:
        d.al_vitales("cama-09", SIGNOS, "jetson-01", vieja)
        d.al_enlace_edge("jetson-01", True)
        d.al_estado_cama("cama-09", "online")
    t = d.tarjetas["cama-09"]
    assert _en_sin_datos(t)
    for avance in (1, 10.5, 60):
        reloj.t = 1000.0 + avance
        d._tick()
        assert _en_sin_datos(t), f"verde o sin etiqueta a +{avance} s"
    # control positivo: la MISMA precondición con vitales en vivo sí da verde
    # (en el orden vital_primero, la 1ª tras el "1" del enlace es la
    # re-publicación del bridge y no cuenta; la siguiente sí)
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts(hace_s=1))
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())
    assert t.punto_estado.bgcolor == VERDE_ONLINE
    assert t.signos["fc"].valor_texto.value == "100"
    assert t.etiqueta_estado.visible is False


# ---- requisito 2: el timeout por el tick ----

def test_timeout_por_el_tick_y_la_vital_fresca_lo_levanta_antes_de_pintar():
    reloj = RelojFalso()
    d, _ = _dashboard(reloj)
    d.al_estado_cama("cama-09", "online")
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts(hace_s=3))
    t = d.tarjetas["cama-09"]
    assert t.punto_estado.bgcolor == VERDE_ONLINE
    reloj.t = 1010.0
    d._tick()
    assert t.punto_estado.bgcolor == VERDE_ONLINE          # 10 s justos: todavía no
    reloj.t = 1010.5
    d._tick()
    assert _en_sin_datos(t)
    assert t.etiqueta_estado.color == bed_card.GRIS_SIN_DATOS
    assert t.signos["fc"].valor_texto.color == GRIS_VALOR
    reloj.t = 1011.0
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())
    assert t.punto_estado.bgcolor == VERDE_ONLINE          # levantada...
    assert t.signos["fc"].valor_texto.value == "100"       # ...y pintada en el mismo turno
    assert t.etiqueta_estado.visible is False


# ---- requisito 3/DUDA 3: las re-entregas no cuentan ----

def test_retenido_al_arrancar_no_cuenta_y_la_primera_en_vivo_si():
    d, _ = _dashboard()
    d.al_enlace_edge("jetson-01", True)
    d.al_estado_cama("cama-09", "online")
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts(hace_s=1), True)   # retain=1
    t = d.tarjetas["cama-09"]
    assert _en_sin_datos(t)
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())                 # en vivo
    assert t.punto_estado.bgcolor == VERDE_ONLINE
    assert t.signos["fc"].valor_texto.value == "100"


def test_mismo_ts_no_repinta_ni_parpadea():
    # el OCR sella al segundo: la segunda vital con el MISMO ts no cuenta, no
    # repinta y no provoca "Sin datos"
    reloj = RelojFalso()
    d, _ = _dashboard(reloj)
    d.al_estado_cama("cama-09", "online")
    ts = _ts()
    d.al_vitales("cama-09", SIGNOS, "jetson-01", ts)
    t = d.tarjetas["cama-09"]
    estados = []
    original = t.aplicar_estado
    t.aplicar_estado = lambda m: (estados.append(m), original(m))
    reloj.t = 1000.5
    d.al_vitales("cama-09", {**SIGNOS, "fc": {"valor": 101}}, "jetson-01", ts)
    assert t.signos["fc"].valor_texto.value == "100"       # no repintó
    assert t.punto_estado.bgcolor == VERDE_ONLINE
    assert t.etiqueta_estado.visible is False
    reloj.t = 1005.0
    d._tick()
    assert estados == []                                   # ni un parpadeo de estado


def test_reentrega_del_retenido_no_borra_una_tarjeta_verde():
    # blip del teléfono: al re-suscribirse le re-entregan la última vital
    # (retain=1, mismo ts): la tarjeta verde sigue verde con sus números
    d, _ = _dashboard()
    d.al_estado_cama("cama-09", "online")
    ts = _ts()
    d.al_vitales("cama-09", SIGNOS, "jetson-01", ts)
    t = d.tarjetas["cama-09"]
    d.al_vitales("cama-09", SIGNOS, "jetson-01", ts, True)
    assert t.punto_estado.bgcolor == VERDE_ONLINE
    assert t.signos["fc"].valor_texto.value == "100"


def test_la_republicacion_del_bridge_tras_el_corte_no_cuenta(pagina_de_signo):
    reloj = RelojFalso()
    d, alertas = _dashboard(reloj)
    d.al_estado_cama("cama-09", "online")
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts(hace_s=25))
    t = d.tarjetas["cama-09"]
    assert t.signos["fc"].valor_texto.value == "100"
    n_alertas = len(alertas)
    d.al_enlace_edge("jetson-01", False)
    reloj.t = 1030.0                                       # el corte duró 30 s
    d.al_enlace_edge("jetson-01", True)
    assert _en_sin_datos(t)
    # el bridge re-publica una vital sellada DURANTE el corte (el teléfono no
    # la vio; su ts es nuevo y está dentro de la frescura): no cuenta
    d.al_vitales("cama-09", FC_FUERA, "jetson-01", _ts(hace_s=20))
    assert _en_sin_datos(t)
    assert len(alertas) == n_alertas and pagina_de_signo.tareas == []
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())    # la siguiente, en vivo
    assert t.punto_estado.bgcolor == VERDE_ONLINE
    assert t.signos["fc"].valor_texto.value == "100"


# ---- requisito 3: en Sin datos (y en Sin conexión) ninguna alerta se evalúa ----

@pytest.mark.parametrize("estado", [SIN_DATOS, "sin_conexion"])
def test_congelada_no_evalua_ninguna_alerta(pagina_de_signo, estado):
    alertas = []
    t = BedCard("cama-09", lambda cama, hay: alertas.append((cama, hay)))
    t.aplicar_estado("online")
    t.actualizar_valor("fc", 30)                           # alerta REAL activa
    fc = t.signos["fc"]
    assert t.estados_alerta["fc"] is True and fc.pulsando is True
    n_alertas, n_tareas = len(alertas), len(pagina_de_signo.tareas)
    t.aplicar_estado(estado)
    t.actualizar_valor("fc", 100)                          # normal...
    t.actualizar_valor("fc", 30)                           # ...y otra vez fuera
    assert t.estados_alerta["fc"] is True                  # congelada, no re-evaluada
    assert fc.pulsando is True and fc.bgcolor == "#3a1616"
    assert fc.valor_texto.value == "--"
    assert t.ultimos_valores == {}
    assert len(alertas) == n_alertas
    assert len(pagina_de_signo.tareas) == n_tareas


def test_secuencia_visual_de_la_etiqueta_y_el_punto():
    t = BedCard("cama-09", lambda *_a: None)
    pasos = [
        ("online", VERDE_ONLINE, False, None, None),
        (SIN_DATOS, GRIS_OFFLINE, True, "Sin datos", bed_card.GRIS_SIN_DATOS),
        ("sin_conexion", AMBAR_SIN_CONEXION, True, "Sin conexión", AMBAR_SIN_CONEXION),
        (SIN_DATOS, GRIS_OFFLINE, True, "Sin datos", bed_card.GRIS_SIN_DATOS),
        ("online", VERDE_ONLINE, False, None, None),
    ]
    for estado, punto, visible, texto, color in pasos:
        t.aplicar_estado(estado)
        assert t.punto_estado.bgcolor == punto, estado
        assert t.etiqueta_estado.visible is visible, estado
        if visible:
            assert t.etiqueta_estado.value == texto, estado
            assert t.etiqueta_estado.color == color, estado
            assert t.signos["fc"].valor_texto.value == "--"
            assert t.signos["fc"].valor_texto.color == GRIS_VALOR


# ---- requisito 2: el timer jamás muere ----

def test_una_excepcion_en_un_tick_no_mata_el_timer(monkeypatch):
    d, _ = _dashboard()
    ticks = []

    def tick():
        ticks.append(1)
        if len(ticks) == 1:
            raise RuntimeError("tick roto")

    def print_roto(*_a, **_k):
        raise OSError("stdout roto")     # hasta el log del except falla

    monkeypatch.setattr(dashboard_mod, "print", print_roto, raising=False)
    d._tick = tick
    dormidas = []

    async def dormir(segundos):
        dormidas.append(segundos)
        if len(dormidas) == 3:
            raise asyncio.CancelledError  # como al cerrar la app

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(d._vigilar(dormir=dormir))
    assert len(ticks) == 3                 # siguió después del tick roto
    assert dormidas == [2, 2, 2]           # ~cada 2 s


def test_una_tarjeta_rota_no_deja_sin_vigilar_a_las_demas():
    reloj = RelojFalso()
    d, _ = _dashboard(reloj)
    for cama in ("cama-09", "cama-10"):
        d.al_estado_cama(cama, "online")
        d.al_vitales(cama, SIGNOS, "jetson-01", _ts())

    def rota(_m):
        raise RuntimeError("tarjeta rota")

    d.tarjetas["cama-09"].aplicar_estado = rota
    reloj.t = 1011.0
    d._tick()
    assert _en_sin_datos(d.tarjetas["cama-10"])


def test_el_tick_solo_aplica_cuando_cambia():
    reloj = RelojFalso()
    d, _ = _dashboard(reloj)
    d.al_estado_cama("cama-09", "online")
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())
    t = d.tarjetas["cama-09"]
    estados = []
    original = t.aplicar_estado
    t.aplicar_estado = lambda m: (estados.append(m), original(m))
    for avance in (2, 4, 6):
        reloj.t = 1000.0 + avance
        d._tick()
    assert estados == []
    for avance in (12, 14):
        reloj.t = 1000.0 + avance
        d._tick()
    assert estados == [SIN_DATOS]


def test_did_mount_arranca_un_solo_timer():
    d, _ = _dashboard()
    d.did_mount()
    d.did_mount()
    assert len(d.page.tareas) == 1


def test_el_reloj_se_inyecta_por_el_constructor():
    reloj = RelojFalso()
    d = Dashboard(lambda _n: None, lambda *_a: None, reloj=reloj)
    assert d._reloj is reloj


def test_por_defecto_el_dashboard_usa_el_reloj_elegido(monkeypatch):
    # requisito 1: el default es el de elegir_reloj (BOOTTIME o monotonic),
    # nunca un reloj de pared
    assert dashboard_mod.RELOJ is conexion.RELOJ
    centinela = lambda: 0.0  # noqa: E731
    monkeypatch.setattr(dashboard_mod, "RELOJ", centinela)
    assert Dashboard(lambda _n: None, lambda *_a: None)._reloj is centinela


def test_al_montar_loguea_el_reloj_una_sola_vez(capsys):
    d, _ = _dashboard()
    d.did_mount()
    d.did_mount()
    salida = capsys.readouterr().out
    assert salida.count(f"reloj {conexion.NOMBRE_RELOJ}") == 1


# ---- requisito 2: el hilo de paho solo ENCOLA; todo corre en el loop ----

def test_paho_solo_encola_en_el_loop():
    d, _ = _dashboard()
    loop = _LoopDiferido()
    d._pagina = _PaginaFalsa(loop)
    d.al_estado_cama("cama-09", "online")
    d.al_enlace_edge("jetson-01", True)
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())
    # nada se tocó desde el "hilo de paho": ni tarjetas ni registro
    assert d.tarjetas == {}
    assert d.conexion.mostrado("cama-09") is None
    assert len(loop.pendientes) == 3
    loop.drenar()                                          # ahora corre el loop
    assert "cama-09" in d.tarjetas
    assert d.conexion.mostrado("cama-09") == "online"


def test_el_loop_procesa_en_orden_de_llegada():
    d, _ = _dashboard()
    loop = _LoopDiferido()
    d._pagina = _PaginaFalsa(loop)
    d.al_enlace_edge("jetson-01", False)                   # llega primero
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())
    loop.drenar()
    t = d.tarjetas["cama-09"]
    assert d.al_montar["punto"] == AMBAR_SIN_CONEXION      # nació "Sin conexión"
    assert t.sin_conexion is True and t.signos["fc"].valor_texto.value == "--"


# ---- el orden registrar_vitales -> clasificar_vital importa ----

def test_cama_nueva_de_un_edge_ya_reconectado_no_cuenta_su_primera_vital(pagina_de_signo):
    reloj = RelojFalso()
    d, alertas = _dashboard(reloj)
    d.al_enlace_edge("jetson-01", False)
    d.al_enlace_edge("jetson-01", True)
    d.al_estado_cama("cama-10", "online")
    # la re-publicación del bridge de una cama que el teléfono nunca vio
    d.al_vitales("cama-10", FC_FUERA, "jetson-01", _ts(hace_s=20))
    t = d.tarjetas["cama-10"]
    assert _en_sin_datos(t)
    assert alertas == [] and pagina_de_signo.tareas == []
    reloj.t += 1
    d.al_vitales("cama-10", SIGNOS, "jetson-01", _ts())
    assert t.punto_estado.bgcolor == VERDE_ONLINE
    assert t.signos["fc"].valor_texto.value == "100"


def test_cama_nueva_con_su_edge_en_0_no_queda_verde_al_volver_el_enlace():
    d, _ = _dashboard()
    d.al_enlace_edge("jetson-01", False)
    d.al_vitales("cama-11", SIGNOS, "jetson-01", _ts())
    t = d.tarjetas["cama-11"]
    assert t.etiqueta_estado.value == "Sin conexión"
    d.al_enlace_edge("jetson-01", True)
    d.al_estado_cama("cama-11", "online")
    assert _en_sin_datos(t)

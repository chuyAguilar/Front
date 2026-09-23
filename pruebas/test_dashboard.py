"""Dashboard + tarjeta reales (flet sin montar): el estado llega a la UI.

Sin página real: `page` se sustituye por una con un loop que ejecuta en el
acto (call_soon_threadsafe inmediato) y update() es no-op en el dashboard.
"""

from datetime import datetime, timedelta, timezone

import pytest

from componentes.bed_card import AMBAR_SIN_CONEXION, GRIS_OFFLINE, VERDE_ONLINE, BedCard
from componentes.signo import Signo
from vistas.dashboard import Dashboard


class _LoopInmediato:
    def call_soon_threadsafe(self, fn, *args):
        fn(*args)


class _PaginaFalsa:
    loop = _LoopInmediato()


class DashboardDePrueba(Dashboard):
    @property
    def page(self):
        return _PaginaFalsa()

    def update(self):
        pass

    def agregar_tarjeta(self, tarjeta):
        # foto de la tarjeta en el instante en que se monta en la pantalla
        self.al_montar = {
            "sin_conexion": tarjeta.sin_conexion,
            "punto": tarjeta.punto_estado.bgcolor,
            "etiqueta": tarjeta.etiqueta_estado.visible,
            "fc": tarjeta.signos["fc"].valor_texto.value,
        }
        super().agregar_tarjeta(tarjeta)


def _dashboard():
    alertas = []
    d = DashboardDePrueba(lambda _n: None, lambda cama, hay: alertas.append((cama, hay)))
    return d, alertas


def _ts(hace_s=0):
    instante = datetime.now(timezone.utc) - timedelta(seconds=hace_s)
    return instante.strftime("%Y-%m-%dT%H:%M:%SZ")


# Valores DENTRO del perfil "adolescente" (el default de la tarjeta): una
# alerta real arranca una animación con page.run_task, que sin página montada
# no existe. Las pruebas de alerta parchean Signo.page (ver `pagina_de_signo`).
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


def test_a_bridge_cero_antes_de_vitales_la_tarjeta_nace_sin_conexion():
    d, _ = _dashboard()
    d.al_enlace_edge("jetson-01", False)                 # llega PRIMERO
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())
    # ya al MONTARSE era "Sin conexión" (no hubo un instante en verde)
    assert d.al_montar == {"sin_conexion": True, "punto": AMBAR_SIN_CONEXION,
                           "etiqueta": True, "fc": "--"}
    t = d.tarjetas["cama-09"]
    assert t.sin_conexion is True
    assert t.punto_estado.bgcolor == AMBAR_SIN_CONEXION
    assert t.etiqueta_estado.visible is True
    # las vitales que llegan durante el corte NO se pintaron: "--" gris
    assert t.signos["fc"].valor_texto.value == "--"
    assert t.ultimos_valores == {}


def test_tarjeta_sin_estado_conocido_nace_gris_no_verde():
    d, _ = _dashboard()
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())
    assert d.al_montar["punto"] == GRIS_OFFLINE
    assert d.tarjetas["cama-09"].punto_estado.bgcolor == GRIS_OFFLINE


def test_sin_conexion_congela_alertas_y_valores():
    d, alertas = _dashboard()
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())
    t = d.tarjetas["cama-09"]
    assert t.signos["fc"].valor_texto.value == "100"
    n_alertas = len(alertas)
    d.al_enlace_edge("jetson-01", False)
    assert t.signos["fc"].valor_texto.value == "--"
    # llegan vitales durante el corte: ni se pintan ni se re-evalúan las alertas
    d.al_vitales("cama-09", FC_FUERA, "jetson-01", _ts())
    assert t.signos["fc"].valor_texto.value == "--"
    assert len(alertas) == n_alertas


def test_alerta_activa_queda_congelada_durante_el_corte(pagina_de_signo):
    d, alertas = _dashboard()
    d.al_vitales("cama-09", FC_FUERA, "jetson-01", _ts())
    t = d.tarjetas["cama-09"]
    fc = t.signos["fc"]
    assert t.estados_alerta["fc"] is True and fc.pulsando is True
    assert alertas[-1] == ("cama-09", True)
    n_alertas = len(alertas)
    d.al_enlace_edge("jetson-01", False)
    # "--" pero la alerta NI se borra NI se re-evalúa
    assert fc.valor_texto.value == "--"
    assert t.estados_alerta["fc"] is True
    assert fc.pulsando is True and fc.bgcolor == "#3a1616"
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())  # normal, pero en el corte
    assert t.estados_alerta["fc"] is True and fc.pulsando is True
    assert len(alertas) == n_alertas


def test_vuelve_el_enlace_muestra_el_estado_de_la_cama_y_luego_datos():
    d, _ = _dashboard()
    d.al_estado_cama("cama-09", "offline")
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())
    t = d.tarjetas["cama-09"]
    assert t.punto_estado.bgcolor == GRIS_OFFLINE
    d.al_enlace_edge("jetson-01", False)
    assert t.punto_estado.bgcolor == AMBAR_SIN_CONEXION
    d.al_enlace_edge("jetson-01", True)                  # 1 NO fuerza online
    assert t.punto_estado.bgcolor == GRIS_OFFLINE
    assert t.etiqueta_estado.visible is False
    d.al_estado_cama("cama-09", "online")
    assert t.punto_estado.bgcolor == VERDE_ONLINE
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())  # datos frescos
    assert t.signos["fc"].valor_texto.value == "100"


def test_al_volver_el_enlace_las_vitales_viejas_no_se_pintan(pagina_de_signo):
    # Hallazgo ALTA de la revisión: al reconectar, el bridge RE-PUBLICA las
    # vitales retenidas del edge (llegan como mensajes en vivo). Si el OCR se
    # cayó durante el corte, esas vitales son de hace minutos.
    d, alertas = _dashboard()
    d.al_estado_cama("cama-09", "online")
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())
    t = d.tarjetas["cama-09"]
    n_alertas = len(alertas)
    d.al_enlace_edge("jetson-01", False)
    d.al_enlace_edge("jetson-01", True)
    d.al_vitales("cama-09", FC_FUERA, "jetson-01", _ts(hace_s=600))
    assert t.signos["fc"].valor_texto.value == "--"
    assert "fc" not in t.ultimos_valores
    assert t.estados_alerta.get("fc") is not True       # ni evaluada
    assert len(alertas) == n_alertas and pagina_de_signo.tareas == []
    # la siguiente vital fresca sí se pinta
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())
    assert t.signos["fc"].valor_texto.value == "100"


def test_vitales_viejas_restauradas_tras_apagon_nacen_en_gris():
    # tras un apagón de la Jetson su broker restaura del disco las vitales
    # retenidas: la tarjeta nace, pero sin números "actuales"
    d, _ = _dashboard()
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts(hace_s=3 * 3600))
    t = d.tarjetas["cama-09"]
    assert t.signos["fc"].valor_texto.value == "--"
    assert t.ultimos_valores == {}


@pytest.mark.parametrize("ts", [None, "", "no-es-fecha", "2026-09-22T10:00:00", 12345])
def test_vitales_sin_ts_legible_fallan_cerrado(ts):
    d, _ = _dashboard()
    d.al_vitales("cama-09", SIGNOS, "jetson-01", ts)
    assert d.tarjetas["cama-09"].signos["fc"].valor_texto.value == "--"


def test_vital_vieja_borra_los_numeros_que_habia():
    d, _ = _dashboard()
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())
    t = d.tarjetas["cama-09"]
    assert t.signos["fc"].valor_texto.value == "100"
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts(hace_s=120))
    assert t.signos["fc"].valor_texto.value == "--"


def test_aplicar_perfil_tras_el_corte_no_resucita_valores_viejos():
    d, _ = _dashboard()
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())
    t = d.tarjetas["cama-09"]
    d.al_enlace_edge("jetson-01", False)
    d.al_enlace_edge("jetson-01", True)
    t.aplicar_perfil(None)                               # "aceptar" del selector
    assert t.signos["fc"].valor_texto.value == "--"


def test_b_la_tarjeta_sigue_a_su_edge_actual():
    d, _ = _dashboard()
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts())
    d.al_vitales("cama-09", SIGNOS, "jetson-02", _ts())  # la cama se movió
    d.al_enlace_edge("jetson-01", False)
    assert d.tarjetas["cama-09"].sin_conexion is False
    d.al_enlace_edge("jetson-02", False)
    assert d.tarjetas["cama-09"].sin_conexion is True


def test_c_vitales_sin_device_id_crean_y_pintan_la_tarjeta():
    d, _ = _dashboard()
    d.al_vitales("cama-10", SIGNOS, None, _ts())         # sin device_id
    assert d.tarjetas["cama-10"].signos["fc"].valor_texto.value == "100"


def test_signo_ausente_no_aborta_la_actualizacion():
    d, _ = _dashboard()
    d.al_vitales("cama-09", {"fc": {"valor": 100}, "pni": {"sis": 70}}, "jetson-01", _ts())
    t = d.tarjetas["cama-09"]
    assert t.signos["fc"].valor_texto.value == "100"
    assert t.signos["spo2"].valor_texto.value == "--"


@pytest.mark.parametrize("mostrado", [None, "offline", "degradado", "", "ONLINE"])
def test_el_verde_solo_se_gana_con_online(mostrado):
    t = BedCard("cama-09", lambda *_a: None)
    assert t.punto_estado.bgcolor == GRIS_OFFLINE        # nace gris
    t.aplicar_estado("online")
    assert t.punto_estado.bgcolor == VERDE_ONLINE
    t.aplicar_estado(mostrado)
    assert t.punto_estado.bgcolor == GRIS_OFFLINE
    assert t.etiqueta_estado.visible is False

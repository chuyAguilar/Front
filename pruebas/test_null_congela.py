"""F1.3 / ADR-025: una lectura null jamás es normal — la app congela la alerta.

Un signo en null (el OCR no leyó el dígito, confianza baja, fuera del rango de
plausibilidad) o ausente/malformado en el mensaje NO se evalúa: se pinta "--"
gris y su alerta queda EXACTAMENTE como estaba. La siguiente lectura numérica
evalúa normal. Mismo criterio que ya tenía la PNI.

Solo importa nombres que ya existían en F1.2 para poder correrlo también contra
f8705cd y mostrar que ahí FALLA.
"""

from datetime import datetime, timedelta, timezone

import pytest

import componentes.bed_card as bed_card
from componentes.bed_card import BedCard
from componentes.signo import Signo
from datos.perfiles import fuera_de_rango
from vistas.dashboard import Dashboard

ROJO = "#3a1616"            # fondo de un signo en alerta (signo.py)
GRIS_VALOR = "#3d5a73"      # color del "--" (signo.py)
# perfil "adolescente" (el default de la tarjeta): (valor normal, fuera de rango)
CASOS = {"fc": (100, 30), "spo2": (97, 80), "fr": (20, 5), "temp": (36.8, 39.5)}


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


@pytest.fixture
def espia(monkeypatch):
    """Registra cada valor con que bed_card llama a fuera_de_rango."""
    recibidos = []

    def fuera_de_rango_espiada(valor, rango):
        recibidos.append(valor)
        return fuera_de_rango(valor, rango)

    monkeypatch.setattr(bed_card, "fuera_de_rango", fuera_de_rango_espiada)
    return recibidos


def _tarjeta():
    alertas = []
    t = BedCard("cama-09", lambda cama, hay: alertas.append((cama, hay)))
    t.aplicar_estado("online")
    return t, alertas


# ---- requisitos 1 y 2, por cada signo ----

@pytest.mark.parametrize("signo", list(CASOS))
def test_activa_null_sigue_activa_normal_la_apaga_fuera_la_enciende(pagina_de_signo, espia, signo):
    normal, fuera = CASOS[signo]
    t, alertas = _tarjeta()
    s = t.signos[signo]
    t.actualizar_valor(signo, fuera)                       # alerta REAL activa
    assert t.estados_alerta[signo] is True and s.pulsando is True
    n_alertas, n_tareas = len(alertas), len(pagina_de_signo.tareas)

    t.actualizar_valor(signo, None)                        # el OCR no lee
    assert s.valor_texto.value == "--" and s.valor_texto.color == GRIS_VALOR
    assert t.estados_alerta[signo] is True                 # exactamente como estaba
    assert s.pulsando is True and s.bgcolor == ROJO
    assert len(alertas) == n_alertas                       # ni al_alerta(False) ni otra
    assert len(pagina_de_signo.tareas) == n_tareas
    assert None not in espia                               # jamás se evaluó el null

    t.actualizar_valor(signo, normal)                      # lectura numérica en rango
    assert normal in espia                                 # (control: el espía sí ve números)
    assert t.estados_alerta[signo] is False
    assert s.pulsando is False and s.bgcolor is None
    assert alertas[-1] == ("cama-09", False)

    t.actualizar_valor(signo, fuera)                       # fuera de rango: se enciende
    assert t.estados_alerta[signo] is True and s.pulsando is True
    assert alertas[-1] == ("cama-09", True)
    assert None not in espia


@pytest.mark.parametrize("signo", list(CASOS))
def test_activa_null_fuera_nunca_se_apaga_en_medio(pagina_de_signo, signo):
    _normal, fuera = CASOS[signo]
    t, alertas = _tarjeta()
    t.actualizar_valor(signo, fuera)
    t.actualizar_valor(signo, None)
    t.actualizar_valor(signo, fuera)
    assert alertas == [("cama-09", True), ("cama-09", True)]   # sin un False en medio
    assert len(pagina_de_signo.tareas) == 1                    # un solo pulso: nunca se apagó


@pytest.mark.parametrize("signo", list(CASOS))
def test_null_sin_alerta_previa_pinta_guiones_y_no_alerta(pagina_de_signo, espia, signo):
    normal, fuera = CASOS[signo]
    t, alertas = _tarjeta()
    s = t.signos[signo]
    t.actualizar_valor(signo, normal)                      # número normal en pantalla
    assert s.valor_texto.value == str(normal)
    n_alertas = len(alertas)
    t.actualizar_valor(signo, None)
    assert s.valor_texto.value == "--" and s.valor_texto.color == GRIS_VALOR
    assert t.estados_alerta[signo] is False                # sigue sin alerta
    assert s.pulsando is False and s.bgcolor is None
    assert len(alertas) == n_alertas and pagina_de_signo.tareas == []
    assert None not in espia
    # el paciente se deteriora: la 1ª lectura anormal tras el null SÍ alerta
    t.actualizar_valor(signo, fuera)
    assert t.estados_alerta[signo] is True
    assert s.pulsando is True and s.bgcolor == ROJO
    assert alertas[-1] == ("cama-09", True)
    assert len(pagina_de_signo.tareas) == 1


def test_cambiar_de_perfil_no_evalua_el_null_guardado(pagina_de_signo):
    t, alertas = _tarjeta()
    t.actualizar_valor("fc", 30)
    t.actualizar_valor("fc", None)
    n_alertas = len(alertas)
    t.dropdown.value = "neonato"
    t.aplicar_perfil(None)                                 # "aceptar" del selector
    fc = t.signos["fc"]
    assert fc.valor_texto.value == "--"                    # no resucita el 30
    assert t.estados_alerta["fc"] is True
    assert fc.pulsando is True and fc.bgcolor == ROJO      # sigue roja
    assert len(alertas) == n_alertas
    assert len(pagina_de_signo.tareas) == 1


def test_fuera_de_rango_sin_lectura_es_no_se_evalua():
    # DUDA 2 aprobada: None -> None ("no se evalúa"), jamás False ("normal")
    assert fuera_de_rango(None, (50, 120)) is None
    assert fuera_de_rango(30, (50, 120)) is True
    assert fuera_de_rango(100, (50, 120)) is False


# ---- por el camino real: una vital que CUENTA con el signo en null/ausente/malformado ----

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


def _ts(hace_s=0):
    instante = datetime.now(timezone.utc) - timedelta(seconds=hace_s)
    return instante.strftime("%Y-%m-%dT%H:%M:%SZ")


SIGNOS = {"fc": {"valor": 30}, "spo2": {"valor": 97}, "fp": {"valor": 99},
          "fr": {"valor": 20}, "temp": {"valor": 36.8}, "pni": None}


@pytest.mark.parametrize("fc", [{"valor": None}, "ausente", 5, {"valor": float("nan")},
                                {"valor": "97"}, {"valor": True}, {"valor": float("inf")}],
                         ids=["null", "ausente", "no_objeto", "nan", "texto", "booleano", "infinito"])
def test_vital_que_cuenta_con_fc_null_no_apaga_la_alerta(pagina_de_signo, fc):
    alertas = []
    d = DashboardDePrueba(lambda _n: None, lambda cama, hay: alertas.append((cama, hay)))
    d.al_estado_cama("cama-09", "online")
    d.al_vitales("cama-09", SIGNOS, "jetson-01", _ts(hace_s=2))     # bradicardia: alerta
    t = d.tarjetas["cama-09"]
    assert t.estados_alerta["fc"] is True
    n_alertas = len(alertas)
    signos = {**SIGNOS, "spo2": {"valor": 96}}
    if fc == "ausente":
        del signos["fc"]
    else:
        signos["fc"] = fc
    d.al_vitales("cama-09", signos, "jetson-01", _ts())             # ts que avanza
    assert t.signos["spo2"].valor_texto.value == "96"               # la vital SÍ contó
    assert t.signos["fc"].valor_texto.value == "--"
    assert t.ultimos_valores["fc"] is None
    assert t.estados_alerta["fc"] is True                           # congelada
    assert t.signos["fc"].pulsando is True and t.signos["fc"].bgcolor == ROJO
    assert ("cama-09", False) not in alertas[n_alertas:]


@pytest.mark.parametrize("pni", [{"sis": "abc", "dia": 70}, {"sis": 120, "dia": None},
                                 {"sis": True, "dia": 70}, {"sis": 120.5, "dia": 70}],
                         ids=["texto", "parcial", "booleano", "no_entero"])
def test_pni_malformada_es_null_y_congela(pagina_de_signo, pni):
    alertas = []
    d = DashboardDePrueba(lambda _n: None, lambda cama, hay: alertas.append((cama, hay)))
    d.al_estado_cama("cama-09", "online")
    d.al_vitales("cama-09", {**SIGNOS, "fc": {"valor": 100}, "pni": {"sis": 180, "dia": 70}},
                 "jetson-01", _ts(hace_s=2))                        # hipertensión: alerta
    t = d.tarjetas["cama-09"]
    assert t.estados_alerta["pni"] is True
    n_alertas = len(alertas)
    d.al_vitales("cama-09", {**SIGNOS, "fc": {"valor": 101}, "pni": pni}, "jetson-01", _ts())
    assert t.signos["fc"].valor_texto.value == "101"                # la vital SÍ contó
    assert t.signos["pni"].valor_texto.value == "--"                # jamás basura en pantalla
    assert t.estados_alerta["pni"] is True                          # congelada
    assert ("cama-09", False) not in alertas[n_alertas:]

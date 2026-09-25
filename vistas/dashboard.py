import asyncio

import flet as ft
from componentes.bed_card import BedCard
from datos.conexion import CUENTA, NOMBRE_RELOJ, RELOJ, VIEJA, RegistroConexion

# Cada cuánto el timer re-evalúa el timeout de datos de las tarjetas: con
# DATOS_MAX_S = 10, "Sin datos" aparece 10-12 s después de la última vital.
PERIODO_VIGILANCIA_S = 2


def _log(texto):
    # hasta el log va protegido: si stdout falla (p. ej. almacenamiento lleno
    # en Android), no puede tumbar ni el timer ni el procesamiento
    try:
        print(texto)
    except Exception:
        pass


class Dashboard(ft.Row):
    """Tarjetas de las camas.

    Un solo dueño del estado: el LOOP de flet. Los tres métodos que llama paho
    desde SU hilo (al_vitales, al_estado_cama, al_enlace_edge) solo encolan
    en el loop con call_soon_threadsafe (FIFO: se conserva el orden de
    llegada). Registro, tarjetas, pintura y timer corren todos en el loop:
    el timer puede recorrer tarjetas y registro sin carreras con los mensajes.
    """

    def __init__(self,al_cambiar_camas,_al_alerta,reloj=None):
        super().__init__()
        #self.camas = ["cama-01", "cama-02", "cama-03", "cama-04", "cama-09", "cama-11"]
        self.tarjetas = {}
        # estado de cada cama, enlace de cada edge, cama -> edge y timeout de
        # datos: lo que se MUESTRA se deriva de ahí (datos/conexion.py), sin
        # importar el orden en que lleguen los mensajes
        self.conexion = RegistroConexion()
        # reloj monotónico del timeout (inyectable en tests)
        self._reloj = reloj or RELOJ
        self._vigilancia = None
        # camas cuya última vital fue vieja (solo para loguear la transición
        # una vez, no a 1 Hz)
        self._camas_con_vital_vieja = set()
        self.controls = []
        self.al_cambiar_camas = al_cambiar_camas
        self._al_alerta = _al_alerta
        self.wrap = True

    def agregar_tarjeta(self,tarjeta):
                        self.controls.append(tarjeta)
                        self.update()

    # ---- timer del timeout de datos (F1.2) ----

    def did_mount(self):
        super().did_mount()
        # did_mount corre una vez por instancia; la guarda es defensiva
        if self._vigilancia is None:
            _log(f"[dashboard] timeout de datos con reloj {NOMBRE_RELOJ}")
            self._vigilancia = self.page.run_task(self._vigilar)

    async def _vigilar(self, dormir=asyncio.sleep, periodo=PERIODO_VIGILANCIA_S):
        # el timer JAMÁS muere por un error: cada tick bajo try. Solo lo
        # termina la cancelación (CancelledError es BaseException) al cerrar.
        while True:
            try:
                self._tick()
            except Exception as e:
                _log(f"[dashboard] tick de vigilancia fallido: {e}")
            await dormir(periodo)

    def _tick(self):
        ahora = self._reloj()
        for cama_id in list(self.tarjetas):
            # cada tarjeta en su propio try: una rota no deja sin vigilar a
            # las demás
            try:
                self._aplicar(cama_id, ahora)
            except Exception as e:
                _log(f"[dashboard] vigilancia de {cama_id} fallida: {e}")

    def _aplicar(self, cama_id, ahora):
        # re-deriva lo que muestra la tarjeta y lo aplica SOLO si cambió
        tarjeta = self.tarjetas.get(cama_id)
        if tarjeta is None:
            return
        mostrado = self.conexion.mostrado_vigente(cama_id, ahora)
        if mostrado != tarjeta.mostrado:
            tarjeta.aplicar_estado(mostrado)

    def _refrescar(self, camas):
        ahora = self._reloj()
        for cama_id in camas:
            self._aplicar(cama_id, ahora)

    # ---- entradas desde el hilo de paho: solo encolan en el loop ----

    def al_estado_cama(self, cama_id, estado):
        self.page.loop.call_soon_threadsafe(self._estado_cama_en_loop, cama_id, estado)

    def al_enlace_edge(self, device_id, conectado):
        self.page.loop.call_soon_threadsafe(self._enlace_edge_en_loop, device_id, conectado)

    def al_vitales(self,cama_id,signos,device_id=None,ts=None,retenido=False):
        self.page.loop.call_soon_threadsafe(
            self._vitales_en_loop, cama_id, signos, device_id, ts, retenido)

    # ---- procesamiento, ya en el loop de flet ----

    def _estado_cama_en_loop(self, cama_id, estado):
        # guarda el ultimo estado (por si la cama aun no tiene tarjeta) y,
        # si ya existe, refresca lo que muestra
        self._refrescar(self.conexion.registrar_estado(cama_id, estado))

    def _enlace_edge_en_loop(self, device_id, conectado):
        # enlace de una Jetson con el server (1/0, o None si desconocido). Se
        # guarda aunque aún no haya tarjetas de ese edge: se aplica al nacer.
        self._refrescar(self.conexion.registrar_enlace(device_id, conectado))

    def _vitales_en_loop(self, cama_id, signos, device_id, ts, retenido):
        ahora = self._reloj()
        # device_id es opcional: sin él la cama se muestra igual
        cambiadas = self.conexion.registrar_vitales(cama_id, device_id)
        # ¿cuenta (fresca y en vivo), es re-entrega/edge en 0, o es vieja?
        clase = self.conexion.clasificar_vital(cama_id, ts, retenido, ahora)

        #crear tarjeta si no existe y contar camas
        if cama_id not in self.tarjetas:
            _log(f"camas descubiertas:  {cama_id}")
            nueva = BedCard(cama_id,self._al_alerta)
            # la tarjeta NACE en su estado final: con lo que ya se sabía de la
            # cama o de su edge ("Sin conexión" si su enlace ya estaba en 0), y
            # "Sin datos" si esta vital no cuenta — nunca verde sin una vital
            # que cuente
            nueva.aplicar_estado(self.conexion.mostrado_vigente(cama_id, ahora))
            self.tarjetas[cama_id] = nueva
            self.agregar_tarjeta(nueva)
            self.al_cambiar_camas(len(self.tarjetas))
        else:
            # la cama cambió de edge: re-derivar (no queda colgada del viejo)
            self._refrescar(cambiadas)
            # una vital que cuenta levanta "Sin datos" ANTES de pintar
            self._aplicar(cama_id, ahora)
        tarjeta = self.tarjetas[cama_id]

        # vital VIEJA (re-publicada por el bridge con el OCR caído, o
        # restaurada del disco del edge tras un apagón): nunca se pinta como
        # actual ni se evalúa para alertas. "--" gris; alertas congeladas.
        if clase == VIEJA:
            tarjeta.borrar_valores()
            if cama_id not in self._camas_con_vital_vieja:
                self._camas_con_vital_vieja.add(cama_id)
                _log(f"[dashboard] vitales de {cama_id} no actuales (ts={ts!r}): se muestran '--'")
            return
        self._camas_con_vital_vieja.discard(cama_id)
        # re-entrega (retain=1, ts que no avanza, 1ª tras reconectar el edge)
        # o edge en 0: ni pinta, ni reinicia el timeout, ni borra
        if clase != CUENTA:
            return

        #extraer valores (un signo ausente o malformado se muestra "--")
        valores = []
        for titulo in ["fc", "spo2", "fp", "fr", "temp"]:
            signo = signos.get(titulo)
            valores.append((titulo, signo.get("valor") if isinstance(signo, dict) else None))

        #ver si signos tiene pni
        pni = signos.get("pni")
        if isinstance(pni, dict) and pni.get("sis") is not None and pni.get("dia") is not None:
            valores.append(("pni", f"{pni['sis']}/{pni['dia']}"))
        else:
            valores.append(("pni", None))

        # cada signo en su propio try: uno roto no impide pintar los demás
        for titulo, valor in valores:
            try:
                tarjeta.actualizar_valor(titulo, valor)
            except Exception as e:
                _log(f"[dashboard] {cama_id}/{titulo} no se pudo pintar: {e}")

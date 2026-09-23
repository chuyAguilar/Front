import flet as ft
from componentes.bed_card import BedCard
from datos.conexion import RegistroConexion, es_fresco

class Dashboard(ft.Row):
    def __init__(self,al_cambiar_camas,_al_alerta):
        super().__init__()
        #self.camas = ["cama-01", "cama-02", "cama-03", "cama-04", "cama-09", "cama-11"]
        self.tarjetas = {}
        # estado de cada cama, enlace de cada edge y cama -> edge: el estado
        # que se MUESTRA se deriva de ahí (datos/conexion.py), sin importar el
        # orden en que lleguen los mensajes
        self.conexion = RegistroConexion()
        # camas cuya última vital no era actual (solo para loguear la
        # transición una vez, no a 1 Hz)
        self._camas_sin_dato_actual = set()
        self.controls = []
        self.al_cambiar_camas = al_cambiar_camas
        self._al_alerta = _al_alerta
        self.wrap = True

    def agregar_tarjeta(self,tarjeta):
                        self.controls.append(tarjeta)
                        self.update()

    def _refrescar(self, camas):
        # re-deriva el estado mostrado de las camas que ya tienen tarjeta
        for cama_id in camas:
            if cama_id in self.tarjetas:
                self.page.loop.call_soon_threadsafe(
                    self.tarjetas[cama_id].aplicar_estado,
                    self.conexion.mostrado(cama_id))

    def al_estado_cama(self, cama_id, estado):
        # guarda el ultimo estado (por si la cama aun no tiene tarjeta) y,
        # si ya existe, refresca lo que muestra
        self._refrescar(self.conexion.registrar_estado(cama_id, estado))

    def al_enlace_edge(self, device_id, conectado):
        # enlace de una Jetson con el server (1/0, o None si desconocido). Se
        # guarda aunque aún no haya tarjetas de ese edge: se aplica al nacer.
        self._refrescar(self.conexion.registrar_enlace(device_id, conectado))

    def al_vitales(self,cama_id,signos,device_id=None,ts=None):
        # device_id es opcional: sin él la cama se muestra igual
        cambiadas = self.conexion.registrar_vitales(cama_id, device_id)

        #crear tarjeta si no existe y contar camas
        if cama_id not in self.tarjetas:
            print("camas descubiertas: ", cama_id)
            nueva = BedCard(cama_id,self._al_alerta)
            # la tarjeta NACE con lo que ya se sabía de esta cama o de su edge
            # (si llegó antes que sus vitales) — incluido "Sin conexión" si el
            # enlace de su edge ya estaba en 0. Sin nada conocido: gris.
            nueva.aplicar_estado(self.conexion.mostrado(cama_id))
            self.tarjetas[cama_id] = nueva
            self.page.loop.call_soon_threadsafe(self.agregar_tarjeta, nueva)

            self.al_cambiar_camas(len(self.tarjetas))
        else:
            # la cama cambió de edge: re-derivar (no queda colgada del viejo)
            self._refrescar(cambiadas)

        # vital VIEJA (re-publicada por el bridge al volver el enlace, o
        # restaurada del disco del edge tras un apagón): nunca se pinta como
        # actual ni se evalúa para alertas. "--" gris; alertas congeladas.
        if not es_fresco(ts):
            self.page.loop.call_soon_threadsafe(self.tarjetas[cama_id].sin_datos_recientes)
            if cama_id not in self._camas_sin_dato_actual:
                self._camas_sin_dato_actual.add(cama_id)
                print(f"[dashboard] vitales de {cama_id} no actuales (ts={ts!r}): se muestran '--'")
            return
        self._camas_sin_dato_actual.discard(cama_id)


        #extraer valores
        titulos = ["fc", "spo2", "fp", "fr", "temp"]
        # fc = datos["signos"]["fc"]["valor"]
        # spo2 = datos["signos"]["spo2"]["valor"]
        # fp = datos["signos"]["fp"]["valor"]
        # fr = datos["signos"]["fr"]["valor"]
        # temp = datos["signos"]["temp"]["valor"]
        
        
        #actualizar valores (un signo ausente o malformado se muestra "--")
        for titulo in titulos:
            signo = signos.get(titulo)
            valor = signo.get("valor") if isinstance(signo, dict) else None
            self.page.loop.call_soon_threadsafe(self.tarjetas[cama_id].actualizar_valor,titulo,valor)

        # self.page.loop.call_soon_threadsafe(self.tarjetas[datos["cama_id"]].actualizar_fc,fc)
        # self.page.loop.call_soon_threadsafe(self.tarjetas[datos["cama_id"]].actualizar_spo2,spo2)
        # self.page.loop.call_soon_threadsafe(self.tarjetas[datos["cama_id"]].actualizar_fp,fp)
        # self.page.loop.call_soon_threadsafe(self.tarjetas[datos["cama_id"]].actualizar_fr,fr)
        # self.page.loop.call_soon_threadsafe(self.tarjetas[datos["cama_id"]].actualizar_temp,temp)

        #ver si signos tiene pni
        pni = signos.get("pni")
        if isinstance(pni, dict) and pni.get("sis") is not None and pni.get("dia") is not None:
            pni_sis = pni["sis"]
            pni_dia = pni["dia"]
            self.page.loop.call_soon_threadsafe(self.tarjetas[cama_id].actualizar_valor,"pni", f"{pni_sis}/{pni_dia}")
        else:
            self.page.loop.call_soon_threadsafe(self.tarjetas[cama_id].actualizar_valor,"pni", None)
       
import flet as ft
from componentes.bed_card import BedCard

class Dashboard(ft.Row):
    def __init__(self,al_cambiar_camas,_al_alerta):
        super().__init__()
        #self.camas = ["cama-01", "cama-02", "cama-03", "cama-04", "cama-09", "cama-11"]
        self.tarjetas = {}
        self.estados = {}
        self.controls = []
        self.al_cambiar_camas = al_cambiar_camas
        self._al_alerta = _al_alerta
        self.wrap = True

    def agregar_tarjeta(self,tarjeta):
                        self.controls.append(tarjeta)
                        self.update()

    def al_estado_cama(self, cama_id, estado):
        # guarda el ultimo estado (por si la cama aun no tiene tarjeta) y,
        # si ya existe, actualiza su puntito online/offline
        self.estados[cama_id] = estado
        if cama_id in self.tarjetas:
            self.page.loop.call_soon_threadsafe(self.tarjetas[cama_id].actualizar_estado, estado)

    def al_vitales(self,cama_id,signos):
        

        #crear tarjeta si no existe y contar camas
        if cama_id not in self.tarjetas:
            print("camas descubiertas: ", cama_id)
            nueva = BedCard(cama_id,self._al_alerta)
            # si ya sabiamos el estado de esta cama (llego antes que sus vitales)
            if cama_id in self.estados:
                nueva.actualizar_estado(self.estados[cama_id])
            self.tarjetas[cama_id] = nueva
            self.page.loop.call_soon_threadsafe(self.agregar_tarjeta, nueva)

            self.al_cambiar_camas(len(self.tarjetas))


        #extraer valores
        titulos = ["fc", "spo2", "fp", "fr", "temp"]
        # fc = datos["signos"]["fc"]["valor"]
        # spo2 = datos["signos"]["spo2"]["valor"]
        # fp = datos["signos"]["fp"]["valor"]
        # fr = datos["signos"]["fr"]["valor"]
        # temp = datos["signos"]["temp"]["valor"]
        
        
        #actualizar valores
        for titulo in titulos:
            valor  = signos[titulo]["valor"]
            self.page.loop.call_soon_threadsafe(self.tarjetas[cama_id].actualizar_valor,titulo,valor)

        # self.page.loop.call_soon_threadsafe(self.tarjetas[datos["cama_id"]].actualizar_fc,fc)
        # self.page.loop.call_soon_threadsafe(self.tarjetas[datos["cama_id"]].actualizar_spo2,spo2)
        # self.page.loop.call_soon_threadsafe(self.tarjetas[datos["cama_id"]].actualizar_fp,fp)
        # self.page.loop.call_soon_threadsafe(self.tarjetas[datos["cama_id"]].actualizar_fr,fr)
        # self.page.loop.call_soon_threadsafe(self.tarjetas[datos["cama_id"]].actualizar_temp,temp)

        #ver si signos tiene pni
        pni = signos["pni"]
        if pni is not None:
            pni_sis = signos["pni"]["sis"]
            pni_dia = signos["pni"]["dia"]
            self.page.loop.call_soon_threadsafe(self.tarjetas[cama_id].actualizar_valor,"pni", f"{pni_sis}/{pni_dia}")
        else:
            self.page.loop.call_soon_threadsafe(self.tarjetas[cama_id].actualizar_valor,"pni", None)
       
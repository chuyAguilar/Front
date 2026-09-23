import flet as ft
from componentes.signo import Signo
from flet_webview import WebView, JavaScriptMode
from datos.perfiles import PERFILES, fuera_de_rango
from datos.conexion import SIN_CONEXION

# Colores del punto de estado de la tarjeta
VERDE_ONLINE = "#00e676"
GRIS_OFFLINE = "#546e7a"
AMBAR_SIN_CONEXION = "#ffb300"

class BedCard(ft.Container):
    def __init__(self, cama_id, al_alerta):
        super().__init__()

        self.perfil = PERFILES["adolescente"]

        # variables
        self.cama_id = cama_id

        # self.etiquetas = {
        #     "fc": "FC",
        #     "spo2": "SpO2",
        #     "fp": "FP",
        #     "fr": "FR",
        #     "temp": "Temperatura",
        #     "pni_sis": "PNI SIS",
        #     "pni_dia": "PNI dia",
        # }

        # self.fc_texto = ft.Text("FC: 120",color=ft.Colors.GREEN)
        # self.spo2_texto = ft.Text("spo2: 50", color=ft.Colors.CYAN)
        # self.fp_text = ft.Text("fp: 50", color= ft.Colors.CYAN)
        # self.fr_text = ft.Text("fr: 50", color = ft.Colors.YELLOW)
        # self.temp_text = ft.Text("temp: 50", color = ft.Colors.WHITE)
        # self.pni_text_sis = ft.Text("pni sis: 50", color = ft.Colors.WHITE)
        # self.pni_text_dia = ft.Text("pni dia: 50", color = ft.Colors.WHITE)

        # propiedades
        self.width = 400
        # self.height = 280
        self.bgcolor = "#0b1623"
        self.padding = 0
        self.alignment = ft.Alignment.CENTER
        self.border_radius = 14
        self.border = ft.Border.all(1,"#1a2d45")

        #hacerlo clickeable
        self.on_click = self.abrir_detalle
        self.ink = True

        #dict para guardar estados en alerta
        self.estados_alerta = {}

        #flag por si está alerta activa
        self.al_alerta = al_alerta

        #"Sin conexión" con el edge (ADR-024): mientras dure, las vitales que
        #lleguen NO se pintan ni se evalúan (serían viejas) y las alertas
        #activas quedan congeladas.
        self.sin_conexion = False


        #Header de card
        #nace GRIS: verde solo cuando se sabe que la cama está online
        self.punto_estado = ft.Container(width=9,height=9,border_radius=5,bgcolor=GRIS_OFFLINE)
        self.etiqueta_estado = ft.Text("Sin conexión", size=11, color=AMBAR_SIN_CONEXION, visible=False)
        self.header = ft.Container(content=ft.Row([
            ft.Text(self.cama_id,),
            self.punto_estado,
            self.etiqueta_estado
        ],alignment=ft.MainAxisAlignment.CENTER ),bgcolor = "#0f1e30",padding=10,border= ft.Border(bottom=ft.BorderSide(1,"#1a2d45")))

        #signos creados con su componente
        self.signos = {
                    "fc": Signo("FC", "lpm",color="#00e676"),
                    "spo2": Signo("SpO2", "%",color= "#00e5ff"),
                    "fp": Signo("FP","lpm", color="#69f0ae"),
                    "fr": Signo("FR", "rpm",color= "#ffee58"),
                    "temp": Signo("TEMP","°c", color="#f5f5f5"),
                    "pni": Signo("PNI","mmHg","#ff7043",ancho = 270)
                    # "pni_sis": Signo("pni sis:","mmHg", color="#ff7043"),
                    # "pni_dia": Signo("pni dia:", "mmHg",color="#ff7043")
                }

        #selector de perfiles
        self.boton_aceptar = ft.TextButton(
            "aceptar",
            on_click=self.aplicar_perfil,
            style=ft.ButtonStyle(
                color="#00e676",
                bgcolor="#12241d",
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
        )
        self.ultimos_valores = {}

        self.dropdown = ft.Dropdown(
            value="adolescente",
            width=220,
            bgcolor="#0f1e30",
            color="#e8f0fe",
            border_color="#1a2d45",
            border_radius=8,
            hint_text="Perfil",
            text_size=13,
            options=[ft.DropdownOption(key=p, text=p) for p in PERFILES],
            )

        
        # contenido
        self.content = ft.Column([
            #Header
            self.header,
            #lista de signos
            ft.Row(list(self.signos.values()),wrap=True,alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([self.dropdown, self.boton_aceptar])

            # self.fc_texto,
            # self.spo2_texto,
            # self.fp_text,
            # self.fr_text,
            # self.temp_text,
            # self.pni_text_sis,
            # self.pni_text_dia,
        ],horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def aplicar_perfil(self,e):
        self.perfil =  PERFILES[self.dropdown.value]
        for s, v in self.ultimos_valores.items(): self.actualizar_valor(s, v)

    #lo que pasa al hacer click
    def abrir_detalle(self,e):
        print("abrir detalle de cama: ", self.cama_id)
        self.webview = WebView(
        url=f"http://100.110.157.112:8000/player.html?base=http://100.110.157.112:8889&cama={self.cama_id}",
   )
        self.dlg = ft.AlertDialog(
            modal=True, 
            title=ft.Text(f"Cama {self.cama_id}", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD, font_family="monospace"), 
            content=ft.Container(
            content=self.webview,
            width=640,
            height=360,
            border_radius=8
            ), 
            bgcolor="#0b1623",
            shape=ft.RoundedRectangleBorder(radius=14),
            content_padding=10,
            actions=[ft.Button("cerrar", 
                                  on_click=lambda e: self.page.pop_dialog())])
        self.page.show_dialog(self.dlg)
        self.page.run_task(self._activar_js)

    async def _activar_js(self):
        await self.webview.set_javascript_mode(JavaScriptMode.UNRESTRICTED)
        await self.webview.reload()


    def actualizar_valor(self, signo, valor):
        #sin conexión con el edge: nada se pinta ni se evalúa (alertas congeladas)
        if self.sin_conexion:
            return

        #actualiza el valor con el valor de signo
        self.signos[signo].actualizar(valor)
        #guardamos cual es el ultimo valor
        self.ultimos_valores[signo] = valor

        #calcular si el signo cruzó su rango del perfil.
        #fuera = None significa "este signo no se evalúa" (fp sin umbral, o pni sin lectura)
        fuera = None
        if signo in self.perfil:
            #signos numéricos simples (fc, spo2, fr, temp)
            fuera = fuera_de_rango(valor, self.perfil[signo])
        elif signo == "pni" and valor is not None:
            #el pni llega como "120/75": se evalúa sis y dia por separado,
            #y la cama está en alerta si CUALQUIERA de los dos cruza su rango
            sis, dia = valor.split("/")
            fuera_sis = fuera_de_rango(int(sis), self.perfil["pni_sis"])
            fuera_dia = fuera_de_rango(int(dia), self.perfil["pni_dia"])
            fuera = fuera_sis or fuera_dia

        #si el signo se evaluó, aplicar visual + detección de cruce + reporte al banner
        if fuera is not None:
            self.signos[signo].alerta(fuera)

            #detección de cruce: sólo avisa en la transición normal -> anormal
            anterior = self.estados_alerta.get(signo, False)
            if fuera is True and anterior is False:
                print("signo a cruzado el limite en la cama: ", self.cama_id)

            #guardar el estado actual del signo
            self.estados_alerta[signo] = fuera

            #reportar al App si la cama tiene alguna alerta activa (para el banner)
            hay_alerta = any(self.estados_alerta.values())
            self.al_alerta(self.cama_id, hay_alerta)


    def sin_datos_recientes(self):
        # sin dato ACTUAL (vital vieja o sin conexión): "--" gris y se olvidan
        # los últimos valores (si no, aplicar_perfil los volvería a pintar como
        # actuales). Las alertas NO se tocan: quedan congeladas.
        for s in self.signos.values():
            s.sin_dato()
        self.ultimos_valores.clear()

    def aplicar_estado(self, mostrado):
        # mostrado (derivado en datos/conexion.py): "sin_conexion", "online",
        # "offline" o None (sin estado conocido).
        #   sin conexión -> punto ámbar + etiqueta; valores "--" gris; alertas
        #                   congeladas (ni se borran ni se re-evalúan)
        #   online       -> punto verde
        #   offline, desconocido o cualquier otro valor -> punto gris (falla
        #                   CERRADO: el verde solo se gana con "online")
        self.sin_conexion = (mostrado == SIN_CONEXION)
        if self.sin_conexion:
            self.punto_estado.bgcolor = AMBAR_SIN_CONEXION
            self.sin_datos_recientes()
        elif mostrado == "online":
            self.punto_estado.bgcolor = VERDE_ONLINE
        else:
            self.punto_estado.bgcolor = GRIS_OFFLINE
        self.etiqueta_estado.visible = self.sin_conexion
        for control in (self.punto_estado, self.etiqueta_estado):
            try:
                control.update()
            except Exception:
                pass
        

    # def actualizar_fc(self, nuevo_valor):
    #     self.fc_texto.value = f"FC: {nuevo_valor}"
    #     try:
    #         self.fc_texto.update()
    #     except Exception:
    #         pass

    # def actualizar_spo2(self, nuevo_valor):
    #         self.spo2_texto.value = f"spo2: {nuevo_valor}"
    #         try:
    #             self.spo2_texto.update()
    #         except Exception:
    #             pass

    # def actualizar_fp(self, nuevo_valor):
    #         self.fp_text.value = f"fp: {nuevo_valor}"
    #         try:
    #             self.fp_text.update()
    #         except Exception:
    #             pass

    # def actualizar_fr(self, nuevo_valor):
    #         self.fr_text.value = f"FR: {nuevo_valor}"
    #         try:
    #             self.fr_text.update()
    #         except Exception:
    #             pass

    # def actualizar_temp(self, nuevo_valor):
    #         self.temp_text.value = f"temp: {nuevo_valor}"
    #         try:
    #             self.temp_text.update()
    #         except Exception:
    #             pass

    # def actualizar_pni_sis(self, nuevo_valor):
    #         self.pni_text_sis.value = f"pni sis: {nuevo_valor}"
    #         try:
    #             self.pni_text_sis.update()
    #         except Exception:
    #             pass

    # def actualizar_pni_dia(self, nuevo_valor):
    #             self.pni_text_dia.value = f"pni dia: {nuevo_valor}"
    #             try:
    #                 self.pni_text_dia.update()
    #             except Exception:
    #                 pass

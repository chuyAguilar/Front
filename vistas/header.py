import flet as ft
from datetime import datetime
import asyncio
from datos.version import VERSION_APP


class Header(ft.Container):
    def __init__(self):
        super().__init__()

        # propiedades

        self.bgcolor = "#0f1e30"
        self.padding = 5
        self.alignment = ft.Alignment.CENTER
        self.border_radius = 5

        # titulo
        self.titulo = ft.Text("monitoreo pediatria by el chuy", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
        #subtitulo
        #la versión va visible para verificar cada teléfono antes de desplegar
        self.subtitulo = ft.Text(f"Ortometa 3d · v{VERSION_APP}", color=ft.Colors.WHITE, weight=ft.FontWeight.NORMAL)

        # mqtt
        self.estado = ft.Text("Conectando MQTT", color=ft.Colors.WHITE)
        self.punto_estado = ft.Container(width=8, height=8, border_radius=4, bgcolor="#546e7a")
        self.pastilla = ft.Container(content=ft.Row([self.punto_estado, self.estado], spacing=6), bgcolor="#12241d", border_radius=20, padding=10)

        #izquierdo
        icono = ft.Container(ft.Icon(ft.Icons.MONITOR_HEART,color="#00e676"),alignment=ft.Alignment.CENTER,bgcolor="#12241d",width=40, height=40, border_radius=10)
        self.izquierdo = ft.Row([icono, ft.Column([self.titulo,self.subtitulo])],spacing = 5)

        #derecho
        self.reloj = ft.Text("--:--:--")
        self.nCamas = ft.Text("0 camas")
        self.derecho = ft.Row([self.reloj,self.nCamas,self.pastilla],spacing=16)

        #header: una sola fila con los dos grupos. El layout se ajusta segun el
        # ancho real de la ventana en _aplicar_layout() (llamado desde did_mount
        # y en cada resize):
        #   ancho  -> wrap=False: space-between empuja el derecho a la orilla derecha.
        #   angosto-> wrap=True: el grupo derecho baja a otra linea (movil).
        self.content = ft.Row(
            [self.izquierdo, self.derecho],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            run_spacing=8,
        )

    def actualizar_estado_mqtt(self, conectado):
        if conectado == True:
            self.estado.value = "MQTT: Conectado"
            self.estado.color = ft.Colors.GREEN_ACCENT
            self.punto_estado.bgcolor = "#00e676"
            self.estado.update()
            self.punto_estado.update()
        else:
            self.estado.value = "MQTT: Desconectado"
            self.estado.color = ft.Colors.RED
            self.punto_estado.bgcolor ="#ff5252"
            self.estado.update()
            self.punto_estado.update()

    def did_mount(self):
        self.page.run_task(self.correr_reloj)
        # layout responsivo: ajusta al montar y en cada cambio de tamaño
        self.page.on_resize = self._al_redimensionar
        self._aplicar_layout()

    def _al_redimensionar(self, e):
        self._aplicar_layout()

    def _aplicar_layout(self):
        # angosto (<600px): wrap para que el derecho baje a otra linea.
        # ancho: sin wrap para que space-between lo empuje a la derecha.
        angosto = bool(self.page.width and self.page.width < 600)
        self.content.wrap = angosto
        # angosto: cada grupo apilado va CENTRADO (se ve limpio en movil).
        # ancho: space-between (izquierdo a la izq, derecho a la der).
        self.content.alignment = (
            ft.MainAxisAlignment.CENTER if angosto else ft.MainAxisAlignment.SPACE_BETWEEN
        )
        try:
            self.content.update()
        except Exception:
            pass

    async def correr_reloj(self):
        while True:
            self.reloj.value = datetime.now().strftime("%H:%M:%S")
            self.reloj.update()
            await asyncio.sleep(1)

    def actualizar_contador_camas(self,n):
        self.nCamas.value = f"{n} camas"
        self.nCamas.update()

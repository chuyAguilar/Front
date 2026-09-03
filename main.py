import flet as ft
import asyncio
from vistas.dashboard import Dashboard
from vistas.header import Header
from servicios.mqtt import ClienteMQTT
from flet_audio import Audio
from flet_android_notifications import FletAndroidNotifications

class App(ft.Container):
    def __init__(self):
        super().__init__()

        self.header = Header()
        self.dashboard = Dashboard(self._al_cambiar_camas, self._al_alerta)
        self.content = ft.Column(
                 controls=[
                      self.header,
                      self.dashboard
                 ]
            )

        self.camas_en_alerta = set()
        self.banner_texto = ft.Text(
            "cama con signos anormales",
            color="#ffe0e0",
            size=15,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
            expand=True,
        )
        # ícono con referencia propia para poder animar su opacidad (latido)
        self.banner_icono = ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color="#ff5252", size=32)
        self.banner_icono.animate_opacity = 500
        self.banner = ft.Banner(
            content=self.banner_texto,
            leading=self.banner_icono,
            actions=[
                ft.TextButton(
                    "cerrar",
                    on_click=lambda e: self.page.pop_dialog(),
                    style=ft.ButtonStyle(
                        color="#ffcdd2",
                        bgcolor="#4a1c1c",
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                )
            ],
            bgcolor="#3a1616",
            elevation=8,
            shadow_color="#000000",
        )
        self.banner_visible = False
        self.banner_pulsando = False

        #creamos una variable que hace referencia al audio de alerta.
        self.audio_alerta = Audio(src="alerta.mp3")

        #creamos una variable que haga referencia al control de vibración
        self.vibracion = ft.HapticFeedback()

        #creamos una variable que haga referencia a las notificaciones
        self.notificaciones = FletAndroidNotifications()

    def _al_estado(self,conectado):
        self.page.loop.call_soon_threadsafe(self.header.actualizar_estado_mqtt, conectado)

    def did_mount(self):
        self.conexion = ClienteMQTT(self.dashboard.al_vitales,self._al_estado,self.dashboard.al_estado_cama)
        self.conexion.iniciar()
        self.page.services.append(self.audio_alerta)
        self.page.services.append(self.vibracion)
        self.page.services.append(self.notificaciones)
        self.page.run_task(self.notificaciones.request_permissions)

    def _al_cambiar_camas(self,n):
        self.page.loop.call_soon_threadsafe(self.header.actualizar_contador_camas, n)

    def _al_alerta(self, cama_id,hay_alerta):
        #print("entra a metodo _al_alerta")
        if hay_alerta == True:
            if cama_id not in self.camas_en_alerta:
                    self.page.run_task(self.audio_alerta.play)
                    self.page.run_task(self._vibrar_alerta)
                    self.page.run_task(self._notificar_alerta,cama_id)
            self.camas_en_alerta.add(cama_id)
        else:
            self.camas_en_alerta.discard(cama_id)
        self.banner_texto.value = f"Alertas en: {', '.join(self.camas_en_alerta)}"
        try:
            self.banner_texto.update()
        except:
            pass
        print("camas en alerta: ",self.camas_en_alerta)
        if self.camas_en_alerta and not self.banner_visible:
            self.page.show_dialog(self.banner)
            self.banner_visible = True
            self.banner_pulsando = True
            self.page.run_task(self._pulso_banner)
        elif not self.camas_en_alerta and self.banner_visible:
            self.page.pop_dialog()
            self.banner_visible = False
            self.banner_pulsando = False

    async def _vibrar_alerta(self):
        await self.vibracion.heavy_impact()
        await asyncio.sleep(0.15)
        await self.vibracion.heavy_impact()
        await asyncio.sleep(0.15)
        await self.vibracion.heavy_impact()
        await asyncio.sleep(0.15)
        await self.vibracion.heavy_impact()
        await asyncio.sleep(0.15)

    async def _notificar_alerta(self,cama_id):
        await self.notificaciones.show_notification(notification_id=int(cama_id.split("-")[1]), title="⚠️ Alerta", body=f"{cama_id} con signos anormales")

    async def _pulso_banner(self):
        # latido del ícono: alterna la opacidad mientras el banner esté visible
        while self.banner_pulsando:
            self.banner_icono.opacity = 0.3
            self.banner_icono.update()
            await asyncio.sleep(0.5)
            self.banner_icono.opacity = 1
            self.banner_icono.update()
            await asyncio.sleep(0.5)

def main(page: ft.Page):
    # card=BedCard("cama 09")
    # page.add(card)
    page.title = "Monitoreo Pediatría by el chuy"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#050b14"
    page.scroll = ft.ScrollMode.AUTO
    page.add(ft.SafeArea(App(), expand=True))


ft.run(main, assets_dir="assets")
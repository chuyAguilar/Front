import flet as ft
import asyncio

class Signo(ft.Container):
    def __init__(self,etiqueta,unidad,color, ancho=85):
            super().__init__()

            self.etiqueta = etiqueta
            self.unidad = unidad
            self.color = color

            self.titulo = ft.Text(etiqueta, size=10,color="#7b9db8")
            self.valor_texto = ft.Text("--", size=28, weight=ft.FontWeight.BOLD, color=color, font_family="monospace")
            self.unidad_valor = ft.Text(unidad,size=10)

            self.pulsando = False

            self.content=ft.Column(
                  controls=[
                self.titulo,
                self.valor_texto,
                self.unidad_valor
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,spacing=2
                )

            self.border = ft.Border(top = ft.BorderSide(2,color))
            self.padding = 5
            self.width = ancho

            self.animate_opacity = 400

    def actualizar(self,valor):
        try:
            if valor is None:
                # sin lectura (cama offline): "--" en gris, sin inventar un número
                self.valor_texto.value = "--"
                self.valor_texto.color = "#3d5a73"
            else:
                self.valor_texto.value = str(valor)
                self.valor_texto.color = self.color
            self.valor_texto.update()
        except:
             print("error en actualizar valor en signo.py")

    def sin_dato(self):
        # Sin dato ACTUAL ("Sin conexión" con el edge, ADR-024; "Sin datos" por
        # timeout, F1.2; o vital vieja):
        # "--" en gris SIN tocar la alerta — las alertas activas quedan
        # congeladas, ni se borran ni se re-evalúan. Silencioso si la tarjeta
        # aún no está montada.
        self.valor_texto.value = "--"
        self.valor_texto.color = "#3d5a73"
        try:
            self.valor_texto.update()
        except Exception:
            pass

    def alerta(self, activa):
         
        self.bgcolor = "#3a1616" if activa else None

        if activa and self.pulsando == False:
             self.pulsando = True
             self.page.run_task(self._pulso)
        elif not activa:
            self.pulsando = False
            self.opacity = 1
        
        try:
            self.update()
        except Exception:
            pass

    async def _pulso(self):
        while self.pulsando:
            self.opacity = 0.4
            self.update()
            await asyncio.sleep(0.5)
            self.opacity = 1
            self.update()
            await asyncio.sleep(0.5)
"""Sirve player.html con las cabeceras CORP + COEP que Flet-web exige
para poder embeberlo en un iframe (WebView). Corre en el puerto 8000.

Uso:  python serve.py   (desde cualquier lado; sirve su propia carpeta)
"""
import http.server
import socketserver
import os

DIRECTORIO = os.path.dirname(os.path.abspath(__file__))
PUERTO = 8000


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Sirve siempre desde la carpeta de este script, no del cwd
        super().__init__(*args, directory=DIRECTORIO, **kwargs)

    def end_headers(self):
        # Sin estas dos, Flet-web (COEP) bloquea el iframe del player
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        super().end_headers()


with socketserver.TCPServer(("", PUERTO), Handler) as httpd:
    print(f"sirviendo player.html en http://127.0.0.1:{PUERTO} (con CORP + COEP)")
    print("Ctrl+C para detener")
    httpd.serve_forever()

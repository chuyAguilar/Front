# La raíz del Front al sys.path para importar servicios/, datos/, vistas/...
# pytest solo vive en el venv: NO va en pyproject.toml ni requirements.txt
# (lo que está ahí viaja dentro del APK). Correr con:
#   .venv\Scripts\python.exe -m pytest pruebas -q
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

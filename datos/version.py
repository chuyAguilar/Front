# Versión visible en el header: permite verificar teléfono por teléfono que
# la app instalada es la correcta (paso 0 del despliegue de ADR-024).
# DEBE coincidir con [project] version de pyproject.toml (lo exige
# pruebas/test_version.py). Al publicar una versión nueva: subir ambas y
# también [tool.flet] build_number (el versionCode de Android).
VERSION_APP = "1.0.6"

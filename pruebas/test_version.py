"""La versión visible en el header coincide con la del APK (pyproject)."""

import os
import re

from datos.version import VERSION_APP

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pyproject():
    with open(os.path.join(RAIZ, "pyproject.toml"), encoding="utf-8") as f:
        return f.read()


def test_version_del_header_igual_a_pyproject():
    m = re.search(r'^version\s*=\s*"([^"]+)"', _pyproject(), re.MULTILINE)
    assert m and m.group(1) == VERSION_APP


def test_build_number_definido():
    # el versionCode explícito: sin él Android recibe siempre 1
    m = re.search(r"^build_number\s*=\s*(\d+)", _pyproject(), re.MULTILINE)
    assert m and int(m.group(1)) >= 2

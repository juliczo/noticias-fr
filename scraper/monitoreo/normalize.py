"""Normalización de texto para el filtrado (Anexo I, punto 2).

Se normalizan por igual el texto de la nota y cada término de la lista:

* a minúsculas,
* se quitan las tildes (á, é, í, ó, ú) y la diéresis,
* se conserva la «ñ»,
* se colapsan los espacios en blanco.

Así «Economía», «ECONOMÍA» y «economia» quedan todas como ``economia`` y ninguna
palabra de la lista queda afuera por un tema de acentuación.
"""

from __future__ import annotations

import re
import unicodedata

_ENYE = "ñ"  # ñ minúscula
# Marca temporal para proteger la «ñ» de la descomposición Unicode.
# Es un carácter del área de uso privado (PUA) que no aparece en texto real.
_MARCA_ENYE = ""

_ESPACIOS = re.compile(r"\s+")
_TOKEN = re.compile(r"[a-z0-9ñ]+")


def normalizar(texto: str | None) -> str:
    """Devuelve ``texto`` en minúsculas, sin tildes, con la «ñ» intacta y espacios colapsados."""
    if not texto:
        return ""
    t = texto.lower().replace(_ENYE, _MARCA_ENYE)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace(_MARCA_ENYE, _ENYE)
    return _ESPACIOS.sub(" ", t).strip()


def tokenizar(texto_normalizado: str) -> list[str]:
    """Parte un texto ya normalizado en palabras (letras a-z, dígitos y «ñ»)."""
    return _TOKEN.findall(texto_normalizado)


def normalizar_tokens(texto: str | None) -> list[str]:
    """Atajo: normaliza y tokeniza en un solo paso."""
    return tokenizar(normalizar(texto))

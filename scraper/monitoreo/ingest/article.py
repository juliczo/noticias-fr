"""Aislamiento del cuerpo del artículo (Anexo I, punto 6).

Se descarta menús, barras laterales y widgets, y se conserva solo el texto de la
nota. Se usa ``trafilatura`` si está disponible; si no, un limpiador de HTML
básico como último recurso.
"""

from __future__ import annotations

import html as _html
import re

_BLOQUE = re.compile(r"<(script|style|noscript|template)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_SALTO = re.compile(r"</(p|div|li|h[1-6]|section|article|br)\s*>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_ESPACIOS_LINEA = re.compile(r"[ \t]+")
_LINEAS = re.compile(r"\n\s*\n\s*")


def _limpiar_html(texto: str) -> str:
    texto = _BLOQUE.sub(" ", texto)
    texto = _SALTO.sub("\n", texto)
    texto = _TAG.sub(" ", texto)
    texto = _html.unescape(texto)
    texto = _ESPACIOS_LINEA.sub(" ", texto)
    texto = _LINEAS.sub("\n\n", texto)
    return texto.strip()


def extraer_cuerpo(html_o_texto: str | None, *, url: str | None = None) -> str:
    """Devuelve el texto del artículo. Acepta HTML o texto ya plano."""
    if not html_o_texto:
        return ""
    contenido = html_o_texto
    parece_html = "<" in contenido and ">" in contenido
    if not parece_html:
        return re.sub(r"[ \t]+", " ", contenido).strip()

    try:
        import trafilatura

        extraido = trafilatura.extract(
            contenido,
            url=url,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        if extraido and len(extraido) >= 120:
            return extraido.strip()
    except Exception:
        pass

    return _limpiar_html(contenido)

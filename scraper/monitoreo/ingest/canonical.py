"""Canonicalización de URLs y hash de contenido (Anexo I, punto 5).

Un mismo artículo suele ser accesible por varias URLs casi iguales (parámetros de
seguimiento, barra final, esquema, ``www``). Se normalizan a una forma única
antes de comparar, para no guardar la misma nota dos veces.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Parámetros de query que son de seguimiento/analítica y no identifican la nota.
_TRACKING = re.compile(
    r"^(utm_.*|fbclid|gclid|gbraid|wbraid|mc_cid|mc_eid|igshid|ref|ref_src|"
    r"spm|_ga|yclid|msclkid|s_cid|vero_id|amp)$",
    re.IGNORECASE,
)
_PUERTOS_POR_DEFECTO = {"http": "80", "https": "443"}


def canonicalizar_url(url: str) -> str:
    """Devuelve una forma canónica de ``url`` para usar como clave de deduplicación."""
    if not url:
        return url
    partes = urlsplit(url.strip())

    esquema = (partes.scheme or "https").lower()
    if esquema == "http":
        esquema = "https"

    host = (partes.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    netloc = host
    if partes.port and _PUERTOS_POR_DEFECTO.get(esquema) != str(partes.port):
        netloc = f"{host}:{partes.port}"

    parametros = [
        (k, v)
        for k, v in parse_qsl(partes.query, keep_blank_values=True)
        if not _TRACKING.match(k)
    ]
    parametros.sort()
    query = urlencode(parametros)

    ruta = re.sub(r"/{2,}", "/", partes.path or "/")
    if len(ruta) > 1 and ruta.endswith("/"):
        ruta = ruta[:-1]

    return urlunsplit((esquema, netloc, ruta, query, ""))  # sin fragmento


def hash_contenido(texto: str | None) -> str:
    """SHA-256 (hex) del texto del artículo, para detectar reediciones."""
    return hashlib.sha256((texto or "").strip().encode("utf-8")).hexdigest()

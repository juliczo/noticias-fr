"""Cliente HTTP para la ingesta (Anexo I, punto 8).

- User-Agent descriptivo que identifica al municipio.
- Tiempo de espera acotado.
- Requests condicionales (If-None-Match / If-Modified-Since) para aligerar.
- Respeto de robots.txt por host (con caché).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib import robotparser
from urllib.parse import urlsplit

_ROBOTS: dict[str, robotparser.RobotFileParser] = {}

# Hostings chicos (varios de nuestros medios lo son) suelen limitar pedidos por
# segundo por IP. Como el runner de GitHub Actions sale a internet desde una IP
# compartida por miles de workflows ajenos, ese límite salta más seguido que
# desde una conexión hogareña. Un respiro mínimo entre pedidos al mismo host
# evita buena parte de esos "429 Too Many Requests".
_ESPACIADO_MIN_SEGUNDOS = 0.6
_ULTIMO_PEDIDO_POR_HOST: dict[str, float] = {}


@dataclass
class Respuesta:
    status: int
    texto: str
    etag: str | None = None
    last_modified: str | None = None
    no_modificado: bool = False


class ClienteHTTP:
    """Envuelve un ``httpx.Client``. Cerrar con ``close()`` o usar como context manager."""

    def __init__(self, user_agent: str, timeout: float = 15.0) -> None:
        import httpx

        self.user_agent = user_agent
        self._cli = httpx.Client(
            headers={
                "User-Agent": user_agent,
                "Accept-Language": "es-AR,es;q=0.9",
            },
            timeout=timeout,
            follow_redirects=True,
        )

    # -- ciclo de vida --
    def close(self) -> None:
        self._cli.close()

    def __enter__(self) -> "ClienteHTTP":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # -- robots.txt --
    def robots_permite(self, url: str) -> bool:
        try:
            p = urlsplit(url)
            base = f"{p.scheme}://{p.netloc}"
            rp = _ROBOTS.get(base)
            if rp is None:
                rp = robotparser.RobotFileParser()
                try:
                    r = self._cli.get(base + "/robots.txt", timeout=8.0)
                    rp.parse(r.text.splitlines() if r.status_code == 200 else [])
                except Exception:
                    rp.parse([])  # sin robots.txt legible -> sin restricciones
                _ROBOTS[base] = rp
            return rp.can_fetch(self.user_agent, url)
        except Exception:
            return True  # ante la duda, permitir (feeds públicos)

    # -- espaciado por host --
    def _esperar_turno(self, url: str) -> None:
        host = urlsplit(url).netloc
        if not host:
            return
        ahora = time.monotonic()
        anterior = _ULTIMO_PEDIDO_POR_HOST.get(host)
        if anterior is not None:
            falta = _ESPACIADO_MIN_SEGUNDOS - (ahora - anterior)
            if falta > 0:
                time.sleep(falta)
        _ULTIMO_PEDIDO_POR_HOST[host] = time.monotonic()

    # -- GET --
    def get(self, url: str, *, etag: str | None = None, last_modified: str | None = None) -> Respuesta:
        import httpx

        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        # Reintentos ante fallos transitorios: cortes de conexión, timeouts,
        # handshakes TLS que fallan una vez y andan al segundo intento, y
        # límites de pedidos por segundo (429/503) que suelen despejarse solos.
        ultimo: Exception | None = None
        for intento in range(3):
            self._esperar_turno(url)
            try:
                r = self._cli.get(url, headers=headers)
            except httpx.TransportError as exc:
                ultimo = exc
                time.sleep(1.5 * (intento + 1))
                continue
            if r.status_code in (429, 503) and intento < 2:
                ultimo = None
                espera = _segundos_retry_after(r.headers.get("Retry-After")) or 2.0 * (intento + 1)
                time.sleep(min(espera, 20.0))
                continue
            break
        else:
            raise ultimo  # type: ignore[misc]

        if r.status_code == 304:
            return Respuesta(304, "", etag, last_modified, no_modificado=True)
        r.raise_for_status()
        return Respuesta(
            r.status_code,
            r.text,
            r.headers.get("ETag"),
            r.headers.get("Last-Modified"),
        )


def _segundos_retry_after(valor: str | None) -> float | None:
    if not valor:
        return None
    try:
        return max(0.0, float(valor))
    except ValueError:
        return None

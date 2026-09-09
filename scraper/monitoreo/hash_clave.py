"""Genera el hash de la clave de acceso para ``docs/clave.js``.

Uso:
    cd sitio-fr/scraper
    python -m monitoreo.hash_clave "la-clave-compartida"

hash = sha256("monitoreo-prensa-zona-oeste|<clave>"). La clave nunca se guarda;
en el sitio solo queda su hash. Es una barrera simple para uso interno.
"""

from __future__ import annotations

import hashlib
import sys

_SALT = "monitoreo-prensa-zona-oeste"


def hash_de(clave: str) -> str:
    return hashlib.sha256(f"{_SALT}|{clave}".encode("utf-8")).hexdigest()


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1]:
        print('Uso: python -m monitoreo.hash_clave "la-clave"', file=sys.stderr)
        return 2
    print()
    print("Pegá esto en docs/clave.js :")
    print()
    print(f'  window.CLAVE_HASH = "{hash_de(sys.argv[1])}";')
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

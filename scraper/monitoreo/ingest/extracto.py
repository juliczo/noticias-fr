"""Construcción del extracto que se guarda por nota (Anexo I, puntos 6 y 9).

No se almacena el cuerpo completo: se guarda un fragmento alrededor de la primera
coincidencia, suficiente para entender de qué trata la nota y para auditar el filtro.
"""

from __future__ import annotations

import re

from ..normalize import normalizar


def construir_extracto(texto: str, patrones: list[str], *, ventana: int = 220) -> str:
    """Fragmento de ``texto`` centrado en la primera aparición de algún patrón.

    ``ventana`` es la cantidad aproximada de caracteres a cada lado. Si no se
    encuentra ningún patrón, devuelve el comienzo del texto.
    """
    if not texto:
        return ""

    plano = re.sub(r"\s+", " ", texto).strip()
    # `base` se usa solo para localizar la coincidencia sin distinguir tildes ni
    # mayúsculas; puede diferir de `plano` en unos pocos caracteres (ligaduras),
    # una imprecisión aceptable para un extracto.
    base = normalizar(plano)

    pos = -1
    for patron in patrones:
        p = normalizar(patron).strip()
        if not p:
            continue
        i = base.find(p)
        if i != -1 and (pos == -1 or i < pos):
            pos = i

    if pos == -1:
        corte = plano[: ventana * 2].rstrip()
        return corte + (" …" if len(plano) > len(corte) else "")

    ini = max(0, pos - ventana)
    fin = min(len(plano), pos + ventana)
    frag = plano[ini:fin].strip()
    if ini > 0:
        frag = "… " + frag
    if fin < len(plano):
        frag = frag + " …"
    return frag

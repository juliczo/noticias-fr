"""Corre una pasada de ingesta y deja el resultado en archivos JSON.

Salida (por defecto en ``sitio/docs/data/``, publicada por GitHub Pages):

* ``notas.json``  — lista de notas detectadas (se acumulan y se podan por antigüedad).
* ``estado.json`` — estado de la última lectura de cada fuente.

Uso:
    cd sitio/scraper
    python -m monitoreo.build
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import ConfigMonitoreo
from .filtering import MotorFiltrado
from .ingest.article import extraer_cuerpo
from .ingest.canonical import canonicalizar_url, hash_contenido
from .ingest.extracto import construir_extracto
from .ingest.net import ClienteHTTP
from .ingest.readers import crear_lector

log = logging.getLogger("monitoreo.build")

RETENCION_DIAS = int(os.environ.get("RETENCION_DIAS", "60"))
MAX_NOTAS = int(os.environ.get("MAX_NOTAS", "400"))
LIMITE_POR_MEDIO = int(os.environ.get("LIMITE_POR_MEDIO", "30"))
MIN_CUERPO = 600

_RAIZ = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("DATA_DIR", _RAIZ / "docs" / "data"))
ZONA = os.environ.get("TZ_APP", "America/Argentina/Buenos_Aires")


# --------------------------------------------------------------------------- #
def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _iso_local(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        return dt.astimezone(ZoneInfo(ZONA)).isoformat()
    except Exception:
        return dt.astimezone(timezone.utc).isoformat()


def _leer_json(nombre: str, por_defecto):
    ruta = DATA_DIR / nombre
    if not ruta.is_file():
        return por_defecto
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return por_defecto


def _escribir_json(nombre: str, datos) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / nombre).write_text(
        json.dumps(datos, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _id_nota(url_canonica: str) -> str:
    return hashlib.sha1(url_canonica.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# Orden de preferencia de canales. Dentro de un mismo nivel se leen TODOS los
# canales y se fusionan (permite, p. ej., varias secciones RSS de un mismo medio).
# Si un nivel trae resultados, no se baja al siguiente.
_NIVELES_CANAL = (("wp_rest",), ("rss", "sitemap"), ("html",))


def _leer_canales(medio, cliente: ClienteHTTP):
    """(crudos_unicos, tipos_ok, errores). Lee el mejor nivel de canales disponible."""
    errores: list[str] = []
    tipos_ok: list[str] = []
    crudos: list = []
    for nivel in _NIVELES_CANAL:
        del_nivel = [c for c in medio.canales if c.tipo in nivel]
        if not del_nivel:
            continue
        # con varios canales del mismo nivel, se reparte el límite
        lim = LIMITE_POR_MEDIO if len(del_nivel) == 1 else max(12, LIMITE_POR_MEDIO // len(del_nivel))
        for canal in del_nivel:
            try:
                got = list(crear_lector(canal, cliente, limite=lim).leer())
            except Exception as exc:
                errores.append(f"{canal.tipo}: {type(exc).__name__}: {exc}")
                continue
            if got:
                crudos.extend(got)
                if canal.tipo not in tipos_ok:
                    tipos_ok.append(canal.tipo)
        if crudos:
            break
    vistas: set[str] = set()
    unicos = []
    for c in crudos:
        u = c.url or ""
        if u and u not in vistas:
            vistas.add(u)
            unicos.append(c)
    return unicos, tipos_ok, errores


def _procesar_medio(medio, motor: MotorFiltrado, cliente: ClienteHTTP, conocidas: set[str], lector=None):
    """Devuelve (lista_de_notas_nuevas, resumen_dict). ``lector`` se inyecta en las pruebas."""
    resumen = {"vistos": 0, "coincidentes": 0, "nuevos": 0, "estado": "ok", "error": None,
               "canal": medio.canales[0].tipo if medio.canales else None}
    nuevas: list[dict] = []

    if lector is None and not medio.canales:
        resumen["estado"] = "error"
        resumen["error"] = "sin canal configurado"
        return nuevas, resumen

    if lector is not None:
        resumen["canal"] = getattr(lector, "canal", resumen["canal"])
        try:
            crudos = list(lector.leer())
        except Exception as exc:
            resumen["estado"] = "error"
            resumen["error"] = f"{type(exc).__name__}: {exc}"[:300]
            return nuevas, resumen
    else:
        crudos, tipos_ok, errores = _leer_canales(medio, cliente)
        resumen["canal"] = ",".join(tipos_ok) or resumen["canal"]
        if not crudos:
            resumen["estado"] = "error"
            resumen["error"] = ("; ".join(errores) or "sin resultados")[:300]
            return nuevas, resumen
        if errores:
            resumen["error"] = ("parcial: " + "; ".join(errores))[:300]

    deteccion = _iso_local(_ahora())
    for crudo in crudos:
        resumen["vistos"] += 1
        if not crudo.url:
            continue
        try:
            url_canon = canonicalizar_url(crudo.url)
            if url_canon in conocidas:
                continue
            cuerpo = crudo.cuerpo_texto or extraer_cuerpo(crudo.cuerpo_html, url=crudo.url)
            if len(cuerpo) < MIN_CUERPO:
                try:
                    if cliente.robots_permite(crudo.url):
                        r = cliente.get(crudo.url)
                        completo = extraer_cuerpo(r.texto, url=crudo.url)
                        if len(completo) > len(cuerpo):
                            cuerpo = completo
                except Exception:
                    pass

            res = motor.evaluar(titulo=crudo.titulo or "", cuerpo=cuerpo)
            if not res.aceptada:
                continue
            resumen["coincidentes"] += 1
            patrones = [c.patron for c in res.coincidencias] + ["morón"]
            nota = {
                "id": _id_nota(url_canon),
                "medio": medio.id,
                "medio_nombre": medio.nombre,
                "canal": crudo.canal,
                "titulo": crudo.titulo or "(sin título)",
                "autor": crudo.autor,
                "url": crudo.url,
                "url_canonica": url_canon,
                "extracto": construir_extracto(cuerpo, patrones),
                "contenido_hash": hash_contenido(cuerpo),
                "niveles": list(res.niveles),
                "terminos": [
                    {"id": c.termino_id, "nivel": c.nivel, "etiqueta_especial": c.etiqueta_especial}
                    for c in res.coincidencias
                ],
                "fecha_publicacion": _iso_local(crudo.fecha_publicacion),
                "fecha_deteccion": deteccion,
            }
            conocidas.add(url_canon)
            nuevas.append(nota)
            resumen["nuevos"] += 1
        except Exception as exc:  # una nota con problema no frena al resto
            log.warning("  %s: nota omitida (%s)", medio.id, exc)

    return nuevas, resumen


def _clave_fecha(n: dict) -> str:
    return n.get("fecha_publicacion") or n.get("fecha_deteccion") or ""


def _dentro_de_ventana(n: dict, corte: datetime) -> bool:
    txt = _clave_fecha(n)
    if not txt:
        return True
    try:
        dt = datetime.fromisoformat(txt)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= corte
    except ValueError:
        return True


# --------------------------------------------------------------------------- #
def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stdout)

    config = ConfigMonitoreo.desde_yaml()
    motor = MotorFiltrado(config)

    viejas = _leer_json("notas.json", [])
    if not isinstance(viejas, list):
        viejas = []
    por_url = {n.get("url_canonica"): n for n in viejas if n.get("url_canonica")}
    conocidas = set(por_url)

    estado_viejo = _leer_json("estado.json", {})
    ok_previo = {
        f.get("id"): f.get("ultima_lectura_ok")
        for f in (estado_viejo.get("fuentes") or [])
    }

    ahora = _ahora()
    ahora_iso = _iso_local(ahora)
    fuentes_estado: list[dict] = []
    total_nuevos = 0
    ids_nuevos: list[str] = []

    with ClienteHTTP(config.ingesta.user_agent, timeout=config.ingesta.timeout_segundos) as cliente:
        for medio in config.medios:
            nuevas, resumen = _procesar_medio(medio, motor, cliente, conocidas)
            for nota in nuevas:
                por_url[nota["url_canonica"]] = nota
                ids_nuevos.append(nota["id"])
            total_nuevos += len(nuevas)
            fuentes_estado.append(
                {
                    "id": medio.id,
                    "nombre": medio.nombre,
                    "canal": resumen["canal"],
                    "estado": resumen["estado"],
                    "vistos": resumen["vistos"],
                    "coincidentes": resumen["coincidentes"],
                    "nuevos": resumen["nuevos"],
                    "error": resumen["error"],
                    "ultima_lectura": ahora_iso,
                    "ultima_lectura_ok": ahora_iso if resumen["estado"] == "ok" else ok_previo.get(medio.id),
                }
            )
            log.info(
                "%-18s [%s] vistos=%d coinc=%d nuevos=%d %s",
                medio.id, resumen["canal"] or "-", resumen["vistos"],
                resumen["coincidentes"], resumen["nuevos"],
                resumen["estado"] + (f" ({resumen['error']})" if resumen["error"] else ""),
            )

    # Poda y orden: primero Nivel B, luego lo más reciente.
    corte = ahora - timedelta(days=RETENCION_DIAS)
    todas = [n for n in por_url.values() if _dentro_de_ventana(n, corte)]
    todas.sort(key=_clave_fecha, reverse=True)
    todas.sort(key=lambda n: 0 if "B" in (n.get("niveles") or []) else 1)
    todas = todas[:MAX_NOTAS]

    _escribir_json("notas.json", todas)
    _escribir_json(
        "estado.json",
        {
            "generado": ahora_iso,
            "intervalo_min": config.ingesta.intervalo_minutos,
            "total_notas": len(todas),
            "nuevas_ultima_corrida": total_nuevos,
            "ids_nuevos": ids_nuevos,
            "fuentes": fuentes_estado,
        },
    )
    log.info("Listo — %d notas en total, %d nuevas en esta corrida.", len(todas), total_nuevos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

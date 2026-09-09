"""Lectores por tipo de canal: wp_rest, rss, html (Anexo I, punto 4).

Cada lector devuelve un iterable de :class:`ArticuloCrudo`. Las librerías propias
de cada canal (``feedparser``) se importan de forma perezosa para que el resto
del paquete se pueda usar sin tenerlas instaladas.
"""

from __future__ import annotations

import html as _html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Protocol
from urllib.parse import urlencode, urljoin, urlsplit

from ..normalize import normalizar
from .net import ClienteHTTP

_TAG = re.compile(r"<[^>]+>")


@dataclass
class ArticuloCrudo:
    url: str
    titulo: str
    canal: str                       # "wp_rest" | "rss" | "html"
    guid: str | None = None
    autor: str | None = None
    fecha_publicacion: datetime | None = None
    cuerpo_html: str | None = None   # HTML del artículo
    cuerpo_texto: str | None = None  # texto ya plano (si la fuente lo entrega así)


class Lector(Protocol):
    canal: str

    def leer(self) -> Iterable[ArticuloCrudo]: ...


# --------------------------------------------------------------------------- #
def crear_lector(canal, cliente: ClienteHTTP, *, limite: int = 25,
                 desde: datetime | None = None) -> Lector:
    """Devuelve el lector correspondiente a ``canal`` (un ``CanalCfg`` del YAML)."""
    if canal.tipo == "wp_rest":
        return LectorWpRest(canal.url, cliente, limite=limite, desde=desde)
    if canal.tipo == "rss":
        return LectorRss(canal.url, cliente, limite=limite)
    if canal.tipo == "sitemap":
        return LectorSitemap(canal.url, cliente, limite=limite)
    if canal.tipo == "html":
        return LectorHtml(canal.url, cliente, limite=limite)
    raise ValueError(f"tipo de canal no soportado: {canal.tipo}")


# --------------------------------------------------------------------------- #
def _texto_plano(html_fragmento: str | None) -> str:
    if not html_fragmento:
        return ""
    return _html.unescape(_TAG.sub("", html_fragmento)).strip()


def _parse_iso(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
class LectorWpRest:
    """API REST de WordPress: /wp-json/wp/v2/posts. Entrega el contenido completo."""

    canal = "wp_rest"

    def __init__(self, url: str, cliente: ClienteHTTP, *, limite: int = 25,
                 desde: datetime | None = None) -> None:
        self.url = url
        self.cli = cliente
        self.limite = limite
        self.desde = desde

    def leer(self) -> Iterable[ArticuloCrudo]:
        params = {"per_page": max(1, min(self.limite, 100)), "_embed": "author"}
        if self.desde:
            params["after"] = self.desde.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
        sep = "&" if "?" in self.url else "?"
        destino = f"{self.url}{sep}{urlencode(params)}"

        if not self.cli.robots_permite(destino):
            return
        resp = self.cli.get(destino)
        if resp.no_modificado:
            return
        try:
            posts = json.loads(resp.texto)
        except json.JSONDecodeError:
            return
        if not isinstance(posts, list):
            return

        for p in posts:
            yield ArticuloCrudo(
                url=p.get("link", ""),
                titulo=_texto_plano((p.get("title") or {}).get("rendered", "")),
                canal=self.canal,
                guid=(p.get("guid") or {}).get("rendered") or str(p.get("id", "")) or None,
                autor=_wp_autor(p),
                fecha_publicacion=_parse_iso(p.get("date_gmt") or p.get("date")),
                cuerpo_html=(p.get("content") or {}).get("rendered") or None,
            )


def _wp_autor(post: dict) -> str | None:
    try:
        return post["_embedded"]["author"][0]["name"] or None
    except (KeyError, IndexError, TypeError):
        return None


# --------------------------------------------------------------------------- #
class LectorRss:
    """Canal RSS. El contenido suele venir truncado; el pipeline completa el cuerpo."""

    canal = "rss"

    def __init__(self, url: str, cliente: ClienteHTTP, *, limite: int = 25) -> None:
        self.url = url
        self.cli = cliente
        self.limite = limite

    def leer(self) -> Iterable[ArticuloCrudo]:
        import feedparser

        if not self.cli.robots_permite(self.url):
            return
        resp = self.cli.get(self.url)
        if resp.no_modificado:
            return
        feed = feedparser.parse(resp.texto)

        for e in feed.entries[: self.limite]:
            cuerpo = ""
            if e.get("content"):
                cuerpo = e["content"][0].get("value", "")
            cuerpo = cuerpo or e.get("summary", "")
            yield ArticuloCrudo(
                url=e.get("link", ""),
                titulo=_texto_plano(e.get("title", "")),
                canal=self.canal,
                guid=e.get("id") or e.get("link") or None,
                autor=e.get("author") or None,
                fecha_publicacion=_fecha_feed(e),
                cuerpo_html=cuerpo or None,
            )


def _fecha_feed(entrada) -> datetime | None:
    import calendar

    st = entrada.get("published_parsed") or entrada.get("updated_parsed")
    if not st:
        return None
    return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc)


# --------------------------------------------------------------------------- #
_SM = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_NEWS = "{http://www.google.com/schemas/sitemap-news/0.9}"


def _menciona_moron(*textos: str) -> bool:
    blob = normalizar(" ".join(t for t in textos if t))
    return "moron" in blob


class LectorSitemap:
    """News sitemap (Google News), para medios sin RSS usable.

    Aplica un pre-filtro por «Morón» sobre el título y la URL: estos sitemaps
    traen decenas o cientos de notas por ciclo y sería abusivo —e inútil—
    descargar todas. La cobertura nacional sobre el municipio prácticamente
    siempre lleva «Morón» en el título o en la URL. El cuerpo completo se
    descarga igual en el pipeline para aplicar el filtro de términos (Nivel A/B).
    """

    canal = "sitemap"

    def __init__(self, url: str, cliente: ClienteHTTP, *, limite: int = 25,
                 pre_filtro: bool = True) -> None:
        self.url = url
        self.cli = cliente
        self.limite = limite
        self.pre_filtro = pre_filtro

    def leer(self) -> Iterable[ArticuloCrudo]:
        import xml.etree.ElementTree as ET

        if not self.cli.robots_permite(self.url):
            return
        resp = self.cli.get(self.url)
        if resp.no_modificado:
            return
        try:
            raiz = ET.fromstring(resp.texto)
        except ET.ParseError:
            return

        rendidas = 0
        for url_el in raiz.iter(f"{_SM}url"):
            if rendidas >= self.limite:
                break
            loc = (url_el.findtext(f"{_SM}loc") or "").strip()
            if not loc:
                continue
            news = url_el.find(f"{_NEWS}news")
            titulo = ""
            fecha = None
            if news is not None:
                titulo = (news.findtext(f"{_NEWS}title") or "").strip()
                fecha = _parse_iso(news.findtext(f"{_NEWS}publication_date"))

            if self.pre_filtro and not _menciona_moron(titulo, loc):
                continue

            rendidas += 1
            yield ArticuloCrudo(
                url=loc,
                titulo=titulo or loc,
                canal=self.canal,
                guid=loc,
                fecha_publicacion=fecha,
            )


# --------------------------------------------------------------------------- #
_NO_ARTICULO = re.compile(
    r"/(tag|tags|categoria|category|seccion|section|secciones|author|autor|page|pagina|"
    r"wp-json|wp-admin|wp-content|wp-includes|feed|assets?|static|dist|build|vendor|"
    r"fonts?|css|js|img|imgs|images|media|cabecera[0-9-]*)/"
    r"|/noticias?-de-[a-z-]+/?($|\?)"          # páginas índice de sección (ej. /noticias-de-moron)
    r"|\.(jpg|jpeg|png|gif|webp|svg|ico|pdf|xml|rss|css|js|mjs|json|woff2?|ttf|eot|"
    r"mp4|mp3|webm|avi|zip|rar)(\?|$)",
    re.IGNORECASE,
)


class LectorHtml:
    """Último recurso: baja una página índice y sigue los enlaces a notas."""

    canal = "html"

    def __init__(self, url: str, cliente: ClienteHTTP, *, limite: int = 25) -> None:
        self.url = url
        self.cli = cliente
        self.limite = limite

    def leer(self) -> Iterable[ArticuloCrudo]:
        if not self.cli.robots_permite(self.url):
            return
        indice = self.cli.get(self.url)
        if indice.no_modificado:
            return

        for enlace in self._enlaces(indice.texto)[: self.limite]:
            if not self.cli.robots_permite(enlace):
                continue
            try:
                pagina = self.cli.get(enlace)
            except Exception:
                continue
            yield ArticuloCrudo(
                url=enlace,
                titulo=_titulo_html(pagina.texto) or enlace,
                canal=self.canal,
                guid=enlace,
                cuerpo_html=pagina.texto,
            )

    def _enlaces(self, html: str) -> list[str]:
        host = urlsplit(self.url).netloc.lower().removeprefix("www.")
        vistos: set[str] = set()
        candidatos: list[tuple[int, int, str]] = []
        for orden, m in enumerate(re.finditer(r'href=["\']([^"\'#]+)["\']', html, re.IGNORECASE)):
            u = urljoin(self.url, m.group(1))
            p = urlsplit(u)
            if p.scheme not in ("http", "https"):
                continue
            if p.netloc.lower().removeprefix("www.") != host:
                continue
            if _NO_ARTICULO.search(p.path):
                continue
            if len(p.path.strip("/")) < 12:  # portada / secciones cortas
                continue
            if u in vistos:
                continue
            vistos.add(u)
            candidatos.append((_puntaje_articulo(p.path), orden, u))
        # Primero los que más parecen una nota (fecha en la ruta, slug largo);
        # a igual puntaje, el orden en que aparecen en la página.
        candidatos.sort(key=lambda c: (-c[0], c[1]))
        return [u for _, _, u in candidatos]


def _puntaje_articulo(path: str) -> int:
    """Cuánto se parece una ruta a la de una nota (más alto = más probable)."""
    if re.search(r"/(?:19|20)\d\d/\d\d?/\d\d?/", path):
        return 3  # /2026/09/08/slug
    ult = path.rstrip("/").rsplit("/", 1)[-1]
    if ult.count("-") >= 3 and len(ult) >= 25:
        return 2  # slug largo con varias palabras
    if re.search(r"/(?:19|20)\d\d/", path) and "-" in ult:
        return 1
    return 0


def _titulo_html(html: str) -> str | None:
    m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', html, re.IGNORECASE)
    if m:
        return _html.unescape(m.group(1)).strip()
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        return _html.unescape(_TAG.sub("", m.group(1))).strip()
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    if m:
        return _html.unescape(_TAG.sub("", m.group(1))).strip()
    return None

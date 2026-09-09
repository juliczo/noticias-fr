from monitoreo.ingest.net import Respuesta
from monitoreo.ingest.readers import LectorSitemap

_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
  <url>
    <loc>https://x.com/politica/moron-aprobo-el-presupuesto-2026-n1</loc>
    <news:news>
      <news:publication><news:name>X</news:name><news:language>es</news:language></news:publication>
      <news:publication_date>2026-09-01T12:00:00Z</news:publication_date>
      <news:title>El Concejo de Morón aprobó el presupuesto</news:title>
    </news:news>
  </url>
  <url>
    <loc>https://x.com/deportes/river-y-boca-empataron-n2</loc>
    <news:news>
      <news:publication><news:name>X</news:name></news:publication>
      <news:publication_date>2026-09-01T11:00:00Z</news:publication_date>
      <news:title>River y Boca empataron el clásico</news:title>
    </news:news>
  </url>
  <url>
    <loc>https://x.com/politica/nota-de-hurlingham-n3</loc>
    <news:news>
      <news:publication><news:name>X</news:name></news:publication>
      <news:publication_date>2026-09-01T10:00:00Z</news:publication_date>
      <news:title>Novedades en el oeste: MORON y alrededores</news:title>
    </news:news>
  </url>
</urlset>
"""


class _CliFake:
    def __init__(self, texto):
        self._texto = texto

    def robots_permite(self, _url):
        return True

    def get(self, _url, **_kw):
        return Respuesta(200, self._texto)


def test_pregate_deja_pasar_solo_las_de_moron_por_titulo_o_url():
    arts = list(LectorSitemap("https://x.com/sitemap-news.xml", _CliFake(_XML)).leer())
    urls = [a.url for a in arts]
    assert urls == [
        "https://x.com/politica/moron-aprobo-el-presupuesto-2026-n1",  # match por URL y título
        "https://x.com/politica/nota-de-hurlingham-n3",                # match por título ("MORON")
    ]
    a0 = arts[0]
    assert a0.canal == "sitemap"
    assert a0.titulo == "El Concejo de Morón aprobó el presupuesto"
    assert a0.fecha_publicacion is not None and a0.fecha_publicacion.year == 2026


def test_pre_filtro_desactivado_devuelve_todo():
    arts = list(LectorSitemap("https://x.com/s.xml", _CliFake(_XML), pre_filtro=False).leer())
    assert len(arts) == 3


def test_respeta_el_limite():
    arts = list(LectorSitemap("https://x.com/s.xml", _CliFake(_XML), limite=1).leer())
    assert len(arts) == 1


def test_xml_invalido_no_rompe():
    arts = list(LectorSitemap("https://x.com/s.xml", _CliFake("no soy xml")).leer())
    assert arts == []

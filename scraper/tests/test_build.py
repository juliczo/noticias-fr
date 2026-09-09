import json

import pytest

from monitoreo import build
from monitoreo.config import ConfigMonitoreo
from monitoreo.filtering import MotorFiltrado
from monitoreo.ingest.readers import ArticuloCrudo


class LectorFake:
    canal = "rss"

    def __init__(self, articulos):
        self._a = articulos

    def leer(self):
        return list(self._a)


class ClienteFake:
    def __init__(self, *args, **kwargs):
        pass

    def robots_permite(self, _u):
        return True

    def get(self, _u, **_k):
        from monitoreo.ingest.net import Respuesta
        return Respuesta(200, "")

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


@pytest.fixture()
def entorno(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(build, "DATA_DIR", data)
    return data


@pytest.fixture(scope="module")
def config():
    return ConfigMonitoreo.desde_yaml()


def _procesar(config, medio_id, articulos, conocidas=None):
    medio = config.medio(medio_id)
    motor = MotorFiltrado(config)
    return build._procesar_medio(
        medio, motor, ClienteFake(),
        conocidas if conocidas is not None else set(),
        lector=LectorFake(articulos),
    )


def test_procesar_medio_filtra_y_arma_notas(config):
    arts = [
        ArticuloCrudo(url="https://www.perfil.com/n1", titulo="El Frente Renovador aprobó su plan",
                      canal="rss", cuerpo_texto="El Concejo de El Frente Renovador aprobó su plan municipal 2026."),
        ArticuloCrudo(url="https://www.perfil.com/n2", titulo="Feria de artesanos",
                      canal="rss", cuerpo_texto="Una feria el fin de semana, sin relación con la gestión."),
    ]
    nuevas, resumen = _procesar(config, "perfil", arts)
    assert resumen["vistos"] == 2
    assert resumen["coincidentes"] == 1
    assert len(nuevas) == 1
    n = nuevas[0]
    assert n["medio"] == "perfil"
    assert "A" in n["niveles"]
    assert "frente_renovador" in [t["id"] for t in n["terminos"]]
    assert n["id"] and n["url_canonica"].startswith("https://")


def test_no_reprocesa_urls_conocidas(config):
    art = [ArticuloCrudo(url="https://www.perfil.com/x?utm_source=rss", titulo="Frente Renovador en campaña",
                         canal="rss", cuerpo_texto="El Frente Renovador debate su estrategia.")]
    conocidas = {"https://perfil.com/x"}
    nuevas, resumen = _procesar(config, "perfil", art, conocidas)
    assert nuevas == []


def test_error_de_fuente_no_rompe(config):
    class LectorRoto:
        canal = "rss"
        def leer(self):
            raise RuntimeError("timeout")

    medio = config.medio("perfil")
    nuevas, resumen = build._procesar_medio(medio, MotorFiltrado(config), ClienteFake(), set(), lector=LectorRoto())
    assert nuevas == []
    assert resumen["estado"] == "error"
    assert "timeout" in resumen["error"]


def test_main_escribe_json_y_acumula(config, entorno, monkeypatch):
    llamados = {"n": 0}

    def fake_procesar(medio, motor, cliente, conocidas):
        llamados["n"] += 1
        if medio.id != "perfil":
            return [], {"vistos": 0, "coincidentes": 0, "nuevos": 0, "estado": "ok", "error": None, "canal": "rss"}
        nota = {
            "id": "abc123", "medio": "perfil", "medio_nombre": "Perfil", "canal": "rss",
            "titulo": "Frente Renovador y la campaña", "autor": None,
            "url": "https://www.perfil.com/z", "url_canonica": "https://www.perfil.com/z",
            "extracto": "…presupuesto…", "contenido_hash": "h",
            "niveles": ["A"], "terminos": [{"id": "frente_renovador", "nivel": "A", "etiqueta_especial": None}],
            "fecha_publicacion": "2026-08-31T09:00:00-03:00", "fecha_deteccion": "2026-08-31T10:00:00-03:00",
        }
        conocidas.add(nota["url_canonica"])
        return [nota], {"vistos": 5, "coincidentes": 1, "nuevos": 1, "estado": "ok", "error": None, "canal": "rss"}

    monkeypatch.setattr(build, "_procesar_medio", fake_procesar)
    monkeypatch.setattr(build, "ClienteHTTP", ClienteFake)

    assert build.main() == 0
    notas = json.loads((entorno / "notas.json").read_text(encoding="utf-8"))
    estado = json.loads((entorno / "estado.json").read_text(encoding="utf-8"))
    assert len(notas) == 1 and notas[0]["id"] == "abc123"
    assert estado["total_notas"] == 1
    assert any(f["id"] == "perfil" and f["estado"] == "ok" for f in estado["fuentes"])

    # Segunda corrida: la misma nota no se duplica.
    assert build.main() == 0
    notas2 = json.loads((entorno / "notas.json").read_text(encoding="utf-8"))
    assert len(notas2) == 1

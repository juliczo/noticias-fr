"""Pruebas del filtro — Monitoreo Frente Renovador.

Reglas:
1. Compuerta AMPLIADA: la nota entra si menciona "frente renovador" O a un
   actor central (Massa, Galmarini, Andreotti, Moreau, Setti, Giuliano,
   Caporiccio, Michel).
2. exigir_termino: false -> alcanza con pasar la compuerta; los niveles solo
   etiquetan y ordenan.
"""

import pytest

from monitoreo.config import ConfigMonitoreo
from monitoreo.filtering import MotorFiltrado


@pytest.fixture(scope="module")
def motor():
    return MotorFiltrado(ConfigMonitoreo.desde_yaml())


def test_config_carga_fr(motor):
    cfg = ConfigMonitoreo.desde_yaml()
    assert cfg.exigir_termino is False
    assert "frente renovador" in cfg.compuerta
    assert len(cfg.medios) == 10


def test_frente_renovador_literal_entra(motor):
    r = motor.evaluar(cuerpo="El Frente Renovador se reunió en su sede de Tigre.")
    assert r.aceptada is True
    assert "frente_renovador" in r.ids_terminos()


def test_actor_central_sin_nombre_del_partido_entra(motor):
    r = motor.evaluar(cuerpo="Sergio Massa viajó a Estados Unidos por una gira de negocios.")
    assert r.aceptada is True
    assert "massa" in r.ids_terminos()


def test_actor_galmarini_entra(motor):
    r = motor.evaluar(cuerpo="Malena Galmarini recorrió obras de agua en el conurbano bonaerense.")
    assert r.aceptada is True


def test_sin_espacio_ni_actor_no_entra(motor):
    r = motor.evaluar(cuerpo="El dólar blue subió y el Gobierno analiza nuevas medidas económicas.")
    assert r.aceptada is False


def test_tema_suelto_no_alcanza_como_compuerta(motor):
    # "peronismo" y "la plata" son etiqueta Nivel B, no compuerta.
    r = motor.evaluar(cuerpo="El peronismo bonaerense discute su estrategia electoral en La Plata.")
    assert r.aceptada is False


def test_niveles_etiquetan_pero_no_filtran(motor):
    r = motor.evaluar(
        cuerpo="Juan Andreotti encabezó en Tigre un acto de la juventud del espacio."
    )
    assert r.aceptada is True
    assert set(r.niveles) == {"A", "B"}
    ids = r.ids_terminos()
    assert "juan_andreotti" in ids and "tigre" in ids and "juventud" in ids


def test_michel_entra(motor):
    r = motor.evaluar(cuerpo="Guillermo Michel dejó la Aduana y evalúa su futuro político.")
    assert r.aceptada is True
    assert "guillermo_michel" in r.ids_terminos()

from monitoreo.ingest.extracto import construir_extracto


def test_fragmento_alrededor_de_la_coincidencia():
    texto = ("bla " * 80) + "El intendente de Morón aprobó el presupuesto municipal. " + ("fin " * 80)
    e = construir_extracto(texto, ["presupuesto"], ventana=60)
    assert "presupuesto" in e.lower()
    assert e.startswith("…") and e.endswith("…")


def test_encuentra_sin_distinguir_tildes():
    e = construir_extracto("La ECONOMÍA de Morón es tema de debate.", ["economia"], ventana=40)
    assert "ECONOMÍA" in e


def test_sin_coincidencia_devuelve_el_comienzo():
    e = construir_extracto("Texto corto y sin ninguno de los patrones buscados.", ["xyz"])
    assert e.startswith("Texto corto")


def test_texto_vacio():
    assert construir_extracto("", ["x"]) == ""

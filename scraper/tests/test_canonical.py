from monitoreo.ingest.canonical import canonicalizar_url, hash_contenido


def test_quita_tracking_y_normaliza_esquema_y_www():
    u = "http://www.elcactus.com.ar/nota/?utm_source=rss&utm_medium=mail&id=5"
    assert canonicalizar_url(u) == "https://elcactus.com.ar/nota?id=5"


def test_saca_barra_final_y_fragmento():
    assert canonicalizar_url("https://x.com/a/b/#seccion") == "https://x.com/a/b"


def test_ordena_los_parametros_restantes():
    assert canonicalizar_url("https://x.com/p?b=2&a=1") == "https://x.com/p?a=1&b=2"


def test_colapsa_barras_repetidas():
    assert canonicalizar_url("https://x.com//a///b") == "https://x.com/a/b"


def test_es_idempotente():
    u = "https://elcactus.com.ar/nota?id=5"
    assert canonicalizar_url(canonicalizar_url(u)) == u


def test_hash_ignora_espacios_de_borde_y_mide_64():
    assert hash_contenido("  hola mundo ") == hash_contenido("hola mundo")
    assert len(hash_contenido("x")) == 64

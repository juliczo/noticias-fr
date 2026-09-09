from monitoreo.normalize import normalizar, normalizar_tokens, tokenizar


def test_minusculas_y_tildes():
    assert normalizar("Morón") == "moron"
    assert normalizar("ECONOMÍA") == "economia"
    assert normalizar("Presupuesto Público") == "presupuesto publico"


def test_conserva_la_enye():
    assert normalizar("Diseño de Ñandú") == "diseño de ñandu"
    assert normalizar("PEÑA") == "peña"


def test_dieresis_y_espacios():
    assert normalizar("pingüino") == "pinguino"
    assert normalizar("  hola\t mundo \n ") == "hola mundo"


def test_entrada_vacia():
    assert normalizar("") == ""
    assert normalizar(None) == ""


def test_tokenizar_ignora_puntuacion():
    assert tokenizar(normalizar("Planificación presupuestaria, en Morón.")) == [
        "planificacion",
        "presupuestaria",
        "en",
        "moron",
    ]


def test_normalizar_tokens_atajo():
    assert normalizar_tokens("La Señora ECONOMÍA") == ["la", "señora", "economia"]

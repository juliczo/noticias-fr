// Hash de la clave de acceso compartida (una sola, sin usuario).
//
// hash = sha256("monitoreo-prensa-zona-oeste|<clave>")
// La clave nunca se guarda: solo su hash. Es una barrera simple para uso
// interno, no una protección fuerte (el JSON de noticias es público).
//
// Para cambiarla:
//   cd scraper && python -m monitoreo.hash_clave "la-nueva-clave"
// (usar la variante de 1 argumento) y pegar el hash acá.

window.CLAVE_HASH = "a1e1e0ab1d5b65308d521942bb04409258114d247fbb25f79ef9410ea7255065";

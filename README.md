# Monitoreo de Prensa — Frente Renovador

Segunda instancia del monitoreo de prensa, con el **mismo funcionamiento** que
el de Morón y **otra estética** (tema oscuro azul). Es un sitio **separado**:
su propio repo, su propio Worker de Cloudflare y su propio Worker de push.

- **Sin servidor ni base de datos.** GitHub Actions corre el scraper y deja el
  resultado en `docs/data/notas.json`.
- **Cloudflare** sirve `docs/` como sitio estático (Worker con `assets`).
- Acceso con **una sola clave compartida** (barrera simple, no seguridad fuerte:
  `notas.json` es un archivo público).

## Filtro

- **Compuerta ampliada:** la nota entra si menciona **"frente renovador"** *o*
  a un **actor central** (Sergio Massa / Massa, Malena Galmarini, Juan Andreotti,
  Eduardo Setti, Cecilia Moreau, Diego Giuliano, Francisco Caporiccio,
  Guillermo Michel).
- `exigir_termino: false` → alcanza con pasar la compuerta. El resto de las
  palabras (juventud, argentina, la plata, tigre, peronismo, cámara de diputados,
  reelecciones indefinidas, fundación encuentro, fr, jóvenes fr…) son
  **etiquetas** Nivel A / B: ordenan y resaltan, no filtran.
- Se cambia todo en `scraper/config/monitoreo.yaml`.

## Medios (10, prensa nacional)

C5N · La Nación · Clarín · La Política Online · Ámbito Financiero · Página 12 ·
TN · El Economista · Infobae · Perfil.

## Publicar (una sola vez)

1. **Repo nuevo en GitHub** (p. ej. `monitoreo-fr`), subir el contenido de esta
   carpeta a la raíz.
2. **Settings → Actions → General →** *Workflow permissions* = **Read and write**.
3. Pestaña **Actions** → "Actualizar noticias (FR)" → *Run workflow* una vez.
4. **Cloudflare → Workers → Create → Connect to Git**, elegir el repo. Usa
   `wrangler.jsonc` (`name: monitoreo-fr`, sirve `./docs`). Queda en
   `https://monitoreo-fr.<subdominio>.workers.dev`.

## Clave de acceso

La actual corresponde a `massapresidente2027`.
Para cambiarla:

```bash
cd scraper
python -m monitoreo.hash_clave "la-nueva-clave"
```

Pegar el `window.CLAVE_HASH = "..."` que imprime en `docs/clave.js` y subir.

## Actualización automática (igual que Morón)

El cron de GitHub es "best-effort". El ritmo puntual (cada ~15 min) lo da el
**Worker de push** de Cloudflare, que en cada corrida le pide a GitHub que
ejecute el scraper (`workflow_dispatch`) y, si hubo notas nuevas, dispara el
push. Ver `push-worker/README.md`. Necesita:

- Un **token fino de GitHub** (permiso *Actions: Read and write* sobre este repo)
  cargado como secret `GH_TOKEN` en el Worker de push, más `GH_REPO` =
  `usuario/monitoreo-fr`.
- Dos secrets de repositorio en GitHub: `PUSH_WORKER_URL` (URL del Worker de push)
  y `PUSH_EMIT_KEY` (cadena al azar, la misma que se carga como secret en el
  Worker de push).

## Notificaciones push

Igual que en Morón: hace falta un **segundo Worker de Cloudflare** (`monitoreo-fr-push`)
con su **propio** par de claves VAPID y su **propio** KV. No se pueden compartir
con los del sitio de Morón. Pasos en `push-worker/README.md`. Mientras
`docs/push-config.js` esté vacío, el panel avisa solo con la pestaña abierta.

## Probar localmente

```bash
cd scraper
pip install -r requirements.txt
python -m monitoreo.build      # genera ../docs/data/*.json
pytest -q

cd ../docs
python -m http.server 8000     # abrir http://localhost:8000
```

# Worker de push — Monitoreo FR

Worker de Cloudflare que:

1. En cada corrida del cron (cada ~15 min, puntual) le pide a GitHub que ejecute
   el scraper (`workflow_dispatch`) y registra la marca de "última verificación".
2. Cuando `notas.json` tiene notas nuevas, manda un push (sin contenido) a cada
   dispositivo suscripto; el service worker del panel se despierta, relee
   `notas.json` y muestra **una notificación por cada noticia nueva**.

El código (`worker.js`) es idéntico al del sitio de Morón: cambia solo la
configuración. **Este Worker es aparte del de Morón** (otro Worker, otro KV,
otras claves VAPID).

## Despliegue (una sola vez)

1. **Claves VAPID** (par nuevo, propio de FR):

   ```bash
   npx web-push generate-vapid-keys
   ```

   Anotá `Public Key` y `Private Key`. Que la pública **no empiece con `-`**
   (si empieza, generá de nuevo).

2. **Cloudflare → Workers → Create Worker**, nombre `monitoreo-fr-push`.
   *Quick edit* → pegar `worker.js` → *Deploy*.

3. **KV**: Workers & Pages → KV → *Create namespace* `SUBS_FR`. En el Worker,
   Settings → Bindings → KV namespace: nombre de variable **`SUBS`**, namespace
   `SUBS_FR`.

4. **Variables y secretos** del Worker (Settings → Variables):

   | Nombre | Tipo | Valor |
   |---|---|---|
   | `VAPID_PUBLIC` | Text | clave pública VAPID |
   | `VAPID_PRIVATE` | Secret | clave privada VAPID |
   | `NOTAS_URL` | Text | `https://monitoreo-fr.<subdominio>.workers.dev/data/notas.json` |
   | `ALLOWED_ORIGIN` | Text | `https://monitoreo-fr.<subdominio>.workers.dev` |
   | `CONTACTO` | Text | un mail de contacto |
   | `GH_TOKEN` | Secret | token fino de GitHub (Actions: Read and write, repo `monitoreo-fr`) |
   | `GH_REPO` | Text | `usuario/monitoreo-fr` |
   | `PUSH_EMIT_KEY` | Secret | cadena al azar (la misma que va como secret de repo en GitHub) |

5. **Cron Trigger**: Settings → Triggers → Cron Triggers → `*/15 * * * *`.

6. **Secrets de repositorio en GitHub** (Settings → Secrets and variables → Actions):

   | Nombre | Valor |
   |---|---|
   | `PUSH_WORKER_URL` | `https://monitoreo-fr-push.<subdominio>.workers.dev` |
   | `PUSH_EMIT_KEY` | la **misma** cadena del paso 4 |

7. **Completar `docs/push-config.js`** en el repo del sitio:

   ```js
   window.PUSH_PUBLIC_KEY = "<clave pública VAPID>";
   window.PUSH_WORKER_URL = "https://monitoreo-fr-push.<subdominio>.workers.dev";
   ```

   Subir el cambio. Mientras esté vacío, el panel avisa solo con la pestaña abierta.

## Diagnóstico

- `GET /estado` → suscripciones, si `NOTAS_URL` responde, qué claves están cargadas.
- `GET /ultimo` → marca de última verificación.
- `GET /probar` → manda un push de prueba a todas las suscripciones (código HTTP por dispositivo).
- `GET /correr` → dispara el scraper ahora (requiere `GH_TOKEN` + `GH_REPO`).
- `POST /emitir` con header `X-Clave: <PUSH_EMIT_KEY>` → lo usa el workflow.

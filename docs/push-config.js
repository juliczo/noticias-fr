// Configuración de las notificaciones push. Se completa DESPUÉS de desplegar el
// Worker de Cloudflare (ver push-worker/README.md).
//
// - PUSH_PUBLIC_KEY: la clave pública VAPID (la misma que va en el Worker).
// - PUSH_WORKER_URL: la URL del Worker, sin barra final.
//
// Mientras estén vacías, el panel usa solo el aviso con la pestaña abierta.

window.PUSH_PUBLIC_KEY = "";
window.PUSH_WORKER_URL = "";

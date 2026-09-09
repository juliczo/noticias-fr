// Cloudflare Worker: recibe suscripciones de notificaciones y envía Web Push
// cuando el archivo de noticias tiene notas nuevas.
//
// El push se manda SIN contenido (solo "despierta" al service worker de la
// página); el service worker vuelve a leer notas.json y arma la notificación.
// Así se evita la parte más compleja (cifrado del payload).
//
// Variables:
//   VAPID_PUBLIC   (var)    clave pública VAPID en base64url
//   VAPID_PRIVATE  (secret) clave privada VAPID en base64url
//   NOTAS_URL      (var)    URL de docs/data/notas.json de la página publicada
//   ALLOWED_ORIGIN (var)    origen del sitio (para CORS)
//   CONTACTO       (var)    mail de contacto (campo "sub" del VAPID)
//   GH_TOKEN       (secret) token fino de GitHub con permiso Actions: Read and write (opcional)
//   GH_REPO        (var)    "usuario/repo" del sitio, ej. Subsepresupuesto/moron-noticias (opcional)
//   GH_BRANCH      (var)    rama por defecto del repo (opcional, default "main")
//   GH_WORKFLOW    (var)    nombre del archivo del workflow (opcional, default "actualizar.yml")
//   PUSH_EMIT_KEY  (secret) clave compartida que autoriza POST /emitir desde el workflow
// KV:
//   SUBS   guarda cada suscripción (sub:<hash>) y el estado (estado:ultimos)
//
// Si GH_TOKEN y GH_REPO están cargadas, en cada corrida del cron el Worker
// también le pide a GitHub que ejecute el scraper (workflow_dispatch). Así la
// actualización de noticias deja de depender del cron de GitHub, que es
// "best-effort" y a veces se atrasa horas.
//
// Endpoints de diagnóstico (abrir en el navegador):
//   GET /estado   -> cuántas suscripciones hay, si NOTAS_URL responde, qué claves están cargadas
//   GET /ultimo   -> marca de "última verificación" (la usa el panel) + resumen de notas.json
//   GET  /probar  -> manda un push de prueba a TODAS las suscripciones e informa el código HTTP de cada una
//   GET  /correr  -> le pide a GitHub que ejecute el scraper ahora mismo (requiere GH_TOKEN + GH_REPO)
//   POST /emitir  -> dispara el push ya (lo llama el workflow); header X-Clave: <PUSH_EMIT_KEY>

export default {
  async fetch(request, env) {
    const cors = {
      "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "*",
      "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };
    if (request.method === "OPTIONS") return new Response(null, { headers: cors });

    const url = new URL(request.url);

    if (url.pathname === "/suscribir" && request.method === "POST") {
      const sub = await safeJson(request);
      if (!sub || !sub.endpoint) return json({ error: "sin endpoint" }, 400, cors);
      await env.SUBS.put("sub:" + (await hash(sub.endpoint)), JSON.stringify(sub));
      return json({ ok: true }, 200, cors);
    }

    if (url.pathname === "/baja" && request.method === "POST") {
      const sub = await safeJson(request);
      if (sub && sub.endpoint) await env.SUBS.delete("sub:" + (await hash(sub.endpoint)));
      return json({ ok: true }, 200, cors);
    }

    if (url.pathname === "/ultimo" && request.method === "GET") {
      const verificacion = await env.SUBS.get("estado:verificacion");
      let notas = null;
      try {
        const r = await fetch(env.NOTAS_URL, { cf: { cacheTtl: 0 } });
        if (r.ok) {
          const arr = await r.json();
          if (Array.isArray(arr)) {
            let ult = null;
            for (const n of arr) {
              const t = n.fecha_deteccion || n.fecha_publicacion;
              if (t && (!ult || t > ult)) ult = t;
            }
            notas = { cantidad: arr.length, ultima_deteccion: ult };
          }
        }
      } catch (e) {}
      return json(
        { verificacion: verificacion || null, ahora: new Date().toISOString(), notas },
        200,
        cors
      );
    }

    if (url.pathname === "/estado" && request.method === "GET") {
      const lista = await env.SUBS.list({ prefix: "sub:" });
      const prev = JSON.parse((await env.SUBS.get("estado:ultimos")) || "null");
      let notas = { ok: false };
      try {
        const r = await fetch(env.NOTAS_URL, { cf: { cacheTtl: 0 } });
        let cuerpo = null;
        try { cuerpo = await r.json(); } catch (e) {}
        notas = {
          ok: r.ok,
          status: r.status,
          cantidad: Array.isArray(cuerpo) ? cuerpo.length : null,
          primeros_ids: Array.isArray(cuerpo) ? cuerpo.slice(0, 3).map((n) => n.id) : null,
        };
      } catch (e) {
        notas = { ok: false, error: String(e) };
      }
      return json(
        {
          suscripciones: lista.keys.length,
          estado_ultimos_cant: prev ? prev.length : null,
          notas_url: env.NOTAS_URL || null,
          notas,
          vapid_public: env.VAPID_PUBLIC || null,
          vapid_private_cargada: !!env.VAPID_PRIVATE,
          allowed_origin: env.ALLOWED_ORIGIN || null,
          contacto: env.CONTACTO || null,
          scraper_auto: !!(env.GH_TOKEN && env.GH_REPO),
          gh_repo: env.GH_REPO || null,
          ultima_verificacion: (await env.SUBS.get("estado:verificacion")) || null,
        },
        200,
        cors
      );
    }

    if (url.pathname === "/correr" && request.method === "GET") {
      if (!env.GH_TOKEN || !env.GH_REPO) {
        return json({ error: "faltan GH_TOKEN o GH_REPO" }, 400, cors);
      }
      const wf = env.GH_WORKFLOW || "actualizar.yml";
      const r = await fetch(
        `https://api.github.com/repos/${env.GH_REPO}/actions/workflows/${wf}/dispatches`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${env.GH_TOKEN}`,
            Accept: "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "moron-prensa-push",
          },
          body: JSON.stringify({ ref: env.GH_BRANCH || "main" }),
        }
      );
      const txt = r.status === 204 ? "" : await r.text();
      return json({ status: r.status, ok: r.status === 204, detalle: txt.slice(0, 300) }, 200, cors);
    }

    if (url.pathname === "/probar" && request.method === "GET") {
      const r = await fanOut(env);
      return json(r, r.error ? 500 : 200, cors);
    }

    // Lo llama el workflow de GitHub apenas comitea notas nuevas: dispara el push
    // en el acto, sin esperar al cron. Protegido con una clave compartida.
    if (url.pathname === "/emitir" && request.method === "POST") {
      if (!env.PUSH_EMIT_KEY || request.headers.get("X-Clave") !== env.PUSH_EMIT_KEY) {
        return json({ error: "no autorizado" }, 401, cors);
      }
      const body = (await safeJson(request)) || {};
      const r = await fanOut(env);
      // realinear la base: prev + ids que informó el workflow + ids actuales de
      // notas.json. Así el cron no vuelve a avisar lo mismo aunque la CDN todavía
      // sirva una versión vieja de notas.json.
      try {
        const prev = JSON.parse((await env.SUBS.get("estado:ultimos")) || "[]");
        const set = new Set(Array.isArray(prev) ? prev : []);
        for (const id of body.ids || []) set.add(id);
        try {
          const rn = await fetch(env.NOTAS_URL, { cf: { cacheTtl: 0 } });
          if (rn.ok) {
            const arr = await rn.json();
            if (Array.isArray(arr)) for (const n of arr) set.add(n.id);
          }
        } catch (e) {}
        await env.SUBS.put("estado:ultimos", JSON.stringify([...set]));
      } catch (e) {}
      return json(r, r.error ? 500 : 200, cors);
    }

    return new Response("Monitoreo de Prensa - push worker", { headers: cors });
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(Promise.allSettled([enviarPushs(env), correrCiclo(env)]));
  },
};

// --------------------------------------------------------------------------- //
// Cada corrida del cron de Cloudflare (puntual): dispara el scraper en GitHub y,
// si GitHub lo aceptó, registra la marca de "última verificación" que muestra el
// panel. Así el panel siempre indica una actualización de hace pocos minutos,
// sin depender del cron "best-effort" de GitHub.
async function correrCiclo(env) {
  const ok = await dispararScraper(env);
  if (ok) {
    try {
      await env.SUBS.put("estado:verificacion", new Date().toISOString());
    } catch (e) {}
  }
}

async function dispararScraper(env) {
  if (!env.GH_TOKEN || !env.GH_REPO) {
    console.log("GH_TOKEN/GH_REPO sin cargar: no se dispara el scraper");
    return false;
  }
  const wf = env.GH_WORKFLOW || "actualizar.yml";
  const url = `https://api.github.com/repos/${env.GH_REPO}/actions/workflows/${wf}/dispatches`;
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "moron-prensa-push",
      },
      body: JSON.stringify({ ref: env.GH_BRANCH || "main" }),
    });
    if (r.status !== 204) {
      const txt = await r.text();
      console.log("dispatch scraper ->", r.status, txt.slice(0, 200));
      return false;
    }
    console.log("dispatch scraper -> 204 OK");
    return true;
  } catch (e) {
    console.log("no se pudo disparar el scraper:", String(e));
    return false;
  }
}

// --------------------------------------------------------------------------- //
async function enviarPushs(env) {
  let notas;
  try {
    const r = await fetch(env.NOTAS_URL, { cf: { cacheTtl: 0 } });
    if (!r.ok) {
      console.log("notas.json respondió", r.status, "- se corta");
      return;
    }
    notas = await r.json();
  } catch (e) {
    console.log("no se pudo leer notas.json:", String(e));
    return;
  }
  if (!Array.isArray(notas)) {
    console.log("notas.json no es un array");
    return;
  }

  const ids = notas.map((n) => n.id);
  const prev = JSON.parse((await env.SUBS.get("estado:ultimos")) || "null");
  await env.SUBS.put("estado:ultimos", JSON.stringify(ids));
  if (!prev) {
    console.log("primera corrida: base fijada con", ids.length, "notas");
    return;
  }
  const nuevos = ids.filter((id) => !prev.includes(id));
  if (!nuevos.length) {
    console.log("sin novedades (", ids.length, "notas )");
    return;
  }
  console.log("novedades:", nuevos.length, "- enviando push");
  const r = await fanOut(env);
  console.log("push enviados:", JSON.stringify(r));
}

// --------------------------------------------------------------------------- //
// Manda el push (sin contenido) a TODAS las suscripciones guardadas.
// Devuelve { enviados, resultados:[{origin,status|error}] } o { error }.
async function fanOut(env) {
  let priv;
  try {
    priv = await importarClave(env.VAPID_PUBLIC, env.VAPID_PRIVATE);
  } catch (e) {
    return { error: "clave VAPID inválida: " + String(e) };
  }
  const contacto = "mailto:" + (env.CONTACTO || "prensa@moron.gob.ar");
  const lista = await env.SUBS.list({ prefix: "sub:" });
  const resultados = [];
  for (const k of lista.keys) {
    const sub = JSON.parse((await env.SUBS.get(k.name)) || "null");
    if (!sub || !sub.endpoint) {
      resultados.push({ key: k.name, error: "suscripción inválida" });
      continue;
    }
    try {
      const status = await enviarUno(env, sub, priv, contacto);
      resultados.push({ origin: safeOrigin(sub.endpoint), status });
      if (status === 404 || status === 410) await env.SUBS.delete(k.name);
    } catch (e) {
      resultados.push({ origin: safeOrigin(sub.endpoint), error: String(e) });
    }
  }
  return { enviados: resultados.length, resultados };
}

async function enviarUno(env, sub, priv, contacto) {
  const jwt = await vapidJWT(new URL(sub.endpoint).origin, priv, contacto);
  const res = await fetch(sub.endpoint, {
    method: "POST",
    headers: {
      TTL: "86400",
      "Content-Length": "0",
      Urgency: "normal",
      Authorization: `vapid t=${jwt}, k=${env.VAPID_PUBLIC}`,
      "Crypto-Key": `p256ecdsa=${env.VAPID_PUBLIC}`,
    },
  });
  return res.status;
}

async function vapidJWT(aud, privKey, sub) {
  const enc = new TextEncoder();
  const header = b64url(enc.encode(JSON.stringify({ typ: "JWT", alg: "ES256" })));
  const payload = b64url(
    enc.encode(JSON.stringify({ aud, exp: Math.floor(Date.now() / 1000) + 12 * 3600, sub }))
  );
  const data = enc.encode(header + "." + payload);
  const sig = new Uint8Array(
    await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, privKey, data)
  );
  return header + "." + payload + "." + b64url(sig);
}

async function importarClave(pubB64, privB64) {
  if (!pubB64 || !privB64) throw new Error("faltan VAPID_PUBLIC o VAPID_PRIVATE");
  const pub = fromB64url(pubB64); // 65 bytes: 0x04 || X(32) || Y(32)
  const jwk = {
    kty: "EC",
    crv: "P-256",
    ext: true,
    x: b64url(pub.slice(1, 33)),
    y: b64url(pub.slice(33, 65)),
    d: privB64.replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_"),
  };
  return crypto.subtle.importKey("jwk", jwk, { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
}

// --------------------------------------------------------------------------- //
function b64url(bytes) {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function fromB64url(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  const bin = atob(s);
  const b = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) b[i] = bin.charCodeAt(i);
  return b;
}
async function hash(s) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return b64url(new Uint8Array(d)).slice(0, 32);
}
function safeOrigin(u) {
  try {
    return new URL(u).origin;
  } catch (e) {
    return "?";
  }
}
async function safeJson(request) {
  try {
    return await request.json();
  } catch (e) {
    return null;
  }
}
function json(obj, status, cors) {
  return new Response(JSON.stringify(obj, null, 2), {
    status,
    headers: { ...cors, "Content-Type": "application/json" },
  });
}

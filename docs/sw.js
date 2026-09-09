// Service worker de Monitoreo de Prensa - Frente Renovador.
// Recibe el "push" (sin contenido) del Worker de Cloudflare, vuelve a leer
// notas.json y muestra una notificación por las noticias que todavía no avisó.

var CACHE = "mp-notif";
var ARCHIVO = "vistos";

self.addEventListener("install", function () {
  self.skipWaiting();
});
self.addEventListener("activate", function (e) {
  e.waitUntil(self.clients.claim());
});

// La página, al suscribirse, manda la lista actual para no avisar retroactivamente.
self.addEventListener("message", function (e) {
  if (e.data && e.data.type === "seed") {
    e.waitUntil(
      caches.open(CACHE).then(function (c) {
        return c.put(ARCHIVO, new Response(JSON.stringify(e.data.ids || [])));
      })
    );
  }
});

// Como máximo esta cantidad de notificaciones individuales por push (si hay
// más noticias nuevas que esto de golpe, el resto se resume en un aviso más).
var MAX_NOTIFS = 12;

self.addEventListener("push", function (event) {
  // Con userVisibleOnly:true el navegador EXIGE que cada push muestre al menos
  // una notificación. Si no, penaliza y termina dando de baja la suscripción.
  // Por eso este handler SIEMPRE llama a showNotification, aunque no logre
  // leer notas.json o no encuentre el detalle de la novedad.
  event.waitUntil(
    (async function () {
      var notas = [];
      try {
        var r = await fetch("./data/notas.json", { cache: "no-store" });
        if (r.ok) { var j = await r.json(); if (Array.isArray(j)) notas = j; }
      } catch (e) {}

      var ids = notas.map(function (n) { return n.id; });
      var cache = await caches.open(CACHE);
      var previa = await cache.match(ARCHIVO);
      var vistos = null;
      if (previa) { try { vistos = await previa.json(); } catch (e) {} }
      await cache.put(ARCHIVO, new Response(JSON.stringify(ids)));

      var nuevas;
      if (vistos && vistos.length) {
        nuevas = notas.filter(function (n) { return vistos.indexOf(n.id) < 0; });
      } else if (notas.length) {
        // sin base previa (recién suscripto): no inundar, avisar solo la última
        nuevas = notas.slice(0, 1);
      } else {
        nuevas = [];
      }

      if (!nuevas.length) {
        await self.registration.showNotification("Monitoreo FR", {
          body: "Hay novedades. Abrí el panel para verlas.",
          tag: "mp-generico",
          data: { url: "./" },
        });
        return;
      }

      var lote = nuevas.slice(0, MAX_NOTIFS);
      for (var i = 0; i < lote.length; i++) {
        var n = lote[i];
        var esNivelA = (n.niveles || []).indexOf("A") >= 0;
        await self.registration.showNotification(n.titulo || "Nueva noticia", {
          body: (n.medio_nombre || n.medio || "") + (esNivelA ? " · menciona a un funcionario" : ""),
          tag: "mp-" + n.id,
          data: { url: "./?nota=" + encodeURIComponent(n.id) },
        });
      }
      if (nuevas.length > lote.length) {
        await self.registration.showNotification("Monitoreo FR", {
          body: "y " + (nuevas.length - lote.length) + " noticias más",
          tag: "mp-mas",
          data: { url: "./" },
        });
      }
    })()
  );
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  var destino = (event.notification.data && event.notification.data.url) || "./";
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then(function (lista) {
        for (var i = 0; i < lista.length; i++) {
          var c = lista[i];
          if ("focus" in c) {
            c.focus();
            if ("navigate" in c) { try { return c.navigate(destino); } catch (e) {} }
            return;
          }
        }
        if (self.clients.openWindow) return self.clients.openWindow(destino);
      })
  );
});

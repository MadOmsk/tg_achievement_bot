// The Mini App's service worker (#164): it shows the app's own notifications
// pushed by the server (bot/services/notifier.py) and opens the app on a tap.
// Deliberately no offline cache: the app is always fresh from the server, and a
// cached copy outliving a deploy would be worse than no copy.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let message = {};
  try {
    message = event.data ? event.data.json() : {};
  } catch {
    message = { body: event.data ? event.data.text() : "" };
  }
  const scope = self.registration.scope;
  event.waitUntil(
    self.registration.showNotification(message.title || "Unlocked", {
      body: message.body || "",
      tag: message.tag || undefined,
      icon: `${scope}logo-192.png`,
      // Android draws the badge as a one-colour shape: the white U, not the tile.
      badge: `${scope}badge-96.png`,
      data: { url: message.url || scope },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || self.registration.scope;
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      // An open copy of the app is reused rather than a second one opened.
      for (const client of windows) {
        if (client.url.startsWith(self.registration.scope) && "navigate" in client) {
          await client.focus();
          return client.navigate(url);
        }
      }
      return self.clients.openWindow(url);
    })(),
  );
});

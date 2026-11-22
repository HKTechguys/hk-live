/* 加到主畫面 + 背景通知（Web Push，空 payload，通知文字由 Worker /alert 取）
   shortcut: 冇離線快取，斷網白畫面；要離線就要另加 app-shell cache。 */
var PUSH_API = "https://hk-live-push.hklive.workers.dev";

self.addEventListener("install", function(){ self.skipWaiting(); });
self.addEventListener("activate", function(e){ e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", function(){});

self.addEventListener("push", function(e){
  e.waitUntil((async function(){
    var a = {};
    try {
      var s = await self.registration.pushManager.getSubscription();
      if (s && PUSH_API) {
        var r = await fetch(PUSH_API + "/alert", {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ endpoint: s.endpoint })
        });
        if (r.ok) a = await r.json();
      }
    } catch(err){}
    var cls = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (var i = 0; i < cls.length; i++) cls[i].postMessage({ type: "hk-push", title: a.title || "" });
    var opt = {
      body: a.body || "路邊咪錶有位，撳開睇邊條街",
      tag: "hk-live", renotify: true, requireInteraction: true,
      vibrate: [140, 70, 140, 70, 220],
      icon: "icon-192.png", badge: "favicon-32.png",
      data: { url: "./index.html#meter" }
    };
    try {
      await self.registration.showNotification(a.title || "HK Live · 有位", opt);
    } catch(err){
      await self.registration.showNotification(a.title || "HK Live · 有位", { body: opt.body, data: opt.data });
    }
  })());
});

self.addEventListener("notificationclick", function(e){
  e.notification.close();
  var u = (e.notification.data && e.notification.data.url) || "./";
  e.waitUntil((async function(){
    var cl = await clients.matchAll({ type: "window", includeUncontrolled: true });
    for (var i = 0; i < cl.length; i++) {
      if (cl[i].url.indexOf("index.html") >= 0 || cl[i].url.indexOf("/hk-live/") >= 0) {
        cl[i].focus();
        try { cl[i].navigate(u); } catch(err){}
        return;
      }
    }
    await clients.openWindow(u);
  })());
});

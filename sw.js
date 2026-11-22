/* 只為「加到主畫面」而存在：唔快取任何請求，避免睇到舊數據。
   shortcut: 冇離線能力，斷網就白畫面；要離線就要加 cache-first 的 app shell。 */
self.addEventListener("install", function(){ self.skipWaiting(); });
self.addEventListener("activate", function(e){ e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", function(){});

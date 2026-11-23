/* HK Live 背景通知 Worker
 * cron 每 2 分鐘：抓運輸署佔用 CSV → 搵「私家車位近 9 分鐘變空置」→ 按訂閱者提醒範圍 push 空通知；
 * sw.js 收到 push 再回 /alert 取文字（唔喺 Worker 做 payload 加密，避開手寫 aes128gcm 風險）。
 * 街道／地區／車輛種類用自己 repo 嘅 data/meters.json（KV 快取 7 日），唔使 parse 政府 CSV 表頭。
 */
const TD = "https://resource.data.one.gov.hk/td/psiparkingspaces";
const MTRS = "https://hktechguys.github.io/hk-live/data/meters.json";
const WINDOW_MS = 9 * 60 * 1000;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "content-type",
  "Access-Control-Allow-Methods": "POST,GET,OPTIONS",
};
const out = (o, s) => new Response(JSON.stringify(o), {
  status: s || 200, headers: { ...CORS, "content-type": "application/json" },
});

export default {
  async fetch(req, env) { return handle(req, env); },
  async scheduled(ev, env, ctx) { ctx.waitUntil(tick(env)); },
};

async function handle(req, env) {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  const url = new URL(req.url);
  try {
    if (url.pathname === "/" || url.pathname === "/health") {
      const l = await env.PUSH_KV.list({ prefix: "sub:" });
      return out({ ok: true, subs: l.keys.length });
    }
    // 香港出行易停車場全量（1,654 個場，含非運輸署場；有實時空位就用 VACANCY）
    if (url.pathname === "/parks") {
      const d = await hkemParks(!!url.searchParams.get("t"));
      return out({ at: d.at, rows: d.rows, uf: await userFees(env) });
    }
    const b = req.method === "POST" ? await req.json().catch(() => null) : null;
    /* 用戶回報收費：{id, h} → KV fee:<id>，之後 /parks 一齊回 */
    if (url.pathname === "/fee" && req.method === "POST") {
      if (!b || !b.id) return out({ error: "missing id" }, 400);
      const h = Math.round(Number(b.h));
      if (!(h > 0 && h <= 3000)) return out({ error: "bad h" }, 400);
      const rec = { h, t: String(b.t || "").slice(0, 48),
        at: new Date(Date.now() + 8 * 3600000).toISOString().slice(0, 16).replace("T", " ") };
      await env.FEE_DB.prepare("INSERT OR REPLACE INTO fee(id,h,t,at) VALUES(?,?,?,?)")
        .bind(String(b.id).slice(0, 40), h, rec.t, rec.at).run();
      FEEC.at = 0;
      return out({ ok: true, rec });
    }
    if (url.pathname === "/subscribe") {
      if (!b || !b.endpoint || !b.sub) return out({ error: "missing" }, 400);
      await env.PUSH_KV.put("sub:" + b.endpoint,
        JSON.stringify({ sub: b.sub, scopes: b.scopes || {}, at: Date.now() }));
      return out({ ok: true });
    }
    if (url.pathname === "/unsubscribe") {
      if (b && b.endpoint) await env.PUSH_KV.delete("sub:" + b.endpoint);
      return out({ ok: true });
    }
    if (url.pathname === "/alert") {
      if (!b || !b.endpoint) return out({}, 400);
      return out((await env.PUSH_KV.get("alert:" + b.endpoint, "json")) || {});
    }
    if (url.pathname === "/test") {
      if (!b || !b.endpoint) return out({ error: "missing endpoint" }, 400);
      await env.PUSH_KV.put("alert:" + b.endpoint, JSON.stringify({
        title: "HK Live 測試通知",
        body: "背景通知已接通，之後有位就用呢個方式通知你。",
        at: Date.now(),
      }), { expirationTtl: 900 });
      const r = await sendPush(b.endpoint, env);
      return out({ ok: true, status: r });
    }
  } catch (e) {
    return out({ error: String(e) }, 500);
  }
  return out({ error: "not found" }, 404);
}

/* ---------- 用戶回報收費（D1，60 秒記憶體快取；KV 免費額度得 1,000 寫入/日唔夠用） ---------- */
let FEEC = { at: 0, o: {} };
async function userFees(env) {
  if (Date.now() - FEEC.at < 60000) return FEEC.o;
  const o = {};
  try {
    const r = await env.FEE_DB.prepare("SELECT id,h,t,at FROM fee LIMIT 5000").all();
    for (const row of (r.results || [])) o[row.id] = { h: row.h, t: row.t, at: row.at };
  } catch (e) {
    return FEEC.o;
  }
  FEEC = { at: Date.now(), o };
  return o;
}

/* ---------- 停車場（香港出行易 DRSS 圖層，需 Referer 才過 403） ---------- */
const HKEM = "https://www.hkemobility.gov.hk/api/drss/layer/map/"
  + "?typeName=DRSS%3AVW_CAR_PARK_TC&service=WFS&version=1.0.0&request=GetFeature"
  + "&outputFormat=application%2Fjson&srsName=EPSG%3A4326";
let PARKC = { at: 0, rows: null };
/* 收費文字藏在 OTHER_INFO／REMARK（PARK_FEE_INFO 全空） */
const ENT = { "&amp": "&", "&lt": "<", "&gt": ">", "&quot": '"', "&#39": "'", "&nbsp": " " };
function feeText(s) {
  if (!s) return "";
  return String(s)
    .replace(/<br\s*\/?>/gi, " / ").replace(/<[^>]+>/g, " ")
    .replace(/&[a-z#0-9]+;/gi, (m) => ENT[m.toLowerCase()] || " ")
    .replace(/\s+/g, " ").trim().slice(0, 240);
}
function feeHourly(s) {
  if (!s) return 0;
  let m = s.match(/(?:每小時|每\s*小時|hourly)[^0-9$]{0,8}(?:HK)?\$?\s*(\d+(?:\.\d+)?)/i)
    || s.match(/\$\s*(\d+(?:\.\d+)?)\s*(?:\/\s*(?:半小時|半個鐘))/)
    || s.match(/\$\s*(\d+(?:\.\d+)?)\s*(?:\/\s*(?:小時|hr))?/);
  if (!m) return 0;
  let v = +m[1];
  if (/半小時|半個鐘/.test(m[0]) && !/每小時/.test(m[0])) v *= 2;
  return v > 0 && v < 500 ? v : 0;
}
async function hkemParks(force) {
  if (!force && PARKC.rows && Date.now() - PARKC.at < 120000) return PARKC;
  const r = await fetch(HKEM, { headers: {
    Referer: "https://www.hkemobility.gov.hk/tc/",
    Origin: "https://www.hkemobility.gov.hk",
    "User-Agent": "Mozilla/5.0",
  }});
  if (!r.ok) throw new Error("hkem " + r.status);
  const j = await r.json();
  const best = new Map();
  for (const f of j.features || []) {
    const p = f.properties || {};
    if (!p.PARK_ID) continue;
    const cur = best.get(p.PARK_ID);
    const isP = p.VEHICLE_TYPE === "P";
    if (cur && !(isP && cur[9] !== "P")) continue; // 每個場留一條，私家車優先
    const c = (f.geometry && f.geometry.coordinates) || [];
    const ft0 = feeText(p.OTHER_INFO || p.REMARK || "");
    const ft = /\$|\uFF04/.test(ft0) ? ft0 : ""; // 只當有價錢嘅文字係收費，避免 EV 充電等無關備註
    best.set(p.PARK_ID, [
      p.EPARK_ID || p.PARK_ID,                                  // 0 id
      p.NAME || "",                                             // 1 名
      p.DISPLAY_ADDRESS || "",                                  // 2 地址
      +(+c[1] || 0).toFixed(5),                                 // 3 lat
      +(+c[0] || 0).toFixed(5),                                 // 4 lng
      typeof p.VACANCY === "number" ? p.VACANCY : -1,            // 5 空位（-1 無數據）
      p.DISTRICT || "",                                         // 6 區
      typeof p.HEIGHT === "number" ? p.HEIGHT : 0,               // 7 高限
      p.LAST_UPDATE || "",                                      // 8 更新時間
      p.VEHICLE_TYPE || "",                                     // 9 種類
      ft,                                                       // 10 收費原文
      feeHourly(ft),                                            // 11 參考時租（0＝未知）
    ]);
  }
  PARKC = { at: Date.now(), rows: [...best.values()] };
  return PARKC;
}

/* ---------- cron ---------- */
async function tick(env) {
  const kv = env.PUSH_KV;
  const subs = (await kv.list({ prefix: "sub:" })).keys;
  if (!subs.length) return;
  const map = await mtrMap(kv);
  const flips = await recentVacant(map);
  if (!flips.length) return;
  const maxT = flips.reduce((a, f) => Math.max(a, f.t), 0);
  for (const k of subs) {
    const rec = await kv.get(k.name, "json");
    if (!rec || !rec.sub) continue;
    const ep = k.name.slice(4);
    const last = (await kv.get("last:" + ep)) || 0;
    const hit = pick(flips.filter((f) => f.t > last), rec.scopes || {}, map);
    if (hit.length) {
      await kv.put("alert:" + ep, JSON.stringify(build(hit, map)), { expirationTtl: 900 });
      const st = await sendPush(ep, env);
      if (st === 404 || st === 410) { await kv.delete(k.name); continue; }
    }
    await kv.put("last:" + ep, String(maxT));
  }
}

function pick(flips, sc, map) {
  const ids = sc.ids || [], streets = sc.streets || [], dists = sc.districts || [];
  if (!ids.length && !streets.length && !dists.length) return [];
  return flips.filter((f) => {
    if (ids.indexOf(f.id) >= 0) return true;
    const m = map[f.id];
    if (!m) return false;
    if (streets.indexOf(m[0]) >= 0) return true;
    if (dists.indexOf(m[1]) >= 0) return true;
    return false;
  }).slice(0, 6);
}

function build(hit, map) {
  const one = hit.length === 1 ? hit[0] : null;
  const st = one && map[one.id] ? map[one.id][0] : "";
  const title = one ? "有位！" + (st || one.id) : "有位！" + hit.length + " 個位剛空出";
  const body = hit.map((f) => {
    const m = map[f.id];
    return m ? f.id + "（" + m[0] + "，" + m[1] + "）" : f.id;
  }).join("、");
  const ids = hit.map((f) => f.id);
  const first = map[ids[0]] || [];
  return { title, body, ids, la: first[3] || 0, lo: first[4] || 0, at: Date.now() };
}

async function recentVacant(map) {
  const txt = await (await fetch(TD + "/occupancystatus/occupancystatus.csv", { cf: { cacheTtl: 60 } })).text();
  const lines = txt.split("\n");
  const now = Date.now();
  const res = [];
  for (let i = 1; i < lines.length; i++) {
    const r = lines[i].split(",");
    if (r.length < 4) continue;
    if ((r[2] || "").trim().toUpperCase() !== "V") continue;
    const id = r[0].trim();
    const m = map[id];
    if (!m || m[2] !== "A") continue;              // 只理私家車（任何車輛）位
    const t = ts2ms(r[3]);
    if (!t || now - t > WINDOW_MS || t > now + 60000) continue;
    res.push({ id, t });
  }
  return res;
}

function ts2ms(s) {
  const m = String(s).match(/(\d+)\/(\d+)\/(\d+)\s+(\d+):(\d+):(\d+)\s*(AM|PM)?/i);
  if (!m) return 0;
  let h = +m[4];
  const ap = (m[7] || "").toUpperCase();
  if (ap === "PM" && h < 12) h += 12;
  if (ap === "AM" && h === 12) h = 0;
  return Date.UTC(+m[3], +m[1] - 1, +m[2], h - 8, +m[5], +m[6]);
}

/* id → [街, 區, 車種, lat, lng]，來源 data/meters.json，KV 快取 7 日 */
async function mtrMap(kv) {
  const c = await kv.get("mtrmap2", "json");
  if (c && c.at && Date.now() - c.at < 7 * 864e5) return c.rows;
  const j = await (await fetch(MTRS, { cf: { cacheTtl: 3600 } })).json();
  const rows = {};
  for (const s of j.spaces || []) rows[String(s[0])] = [s[4] || "", s[5] || "", s[6] || "", s[1], s[2]];
  await kv.put("mtrmap2", JSON.stringify({ at: Date.now(), rows }));
  return rows;
}

/* ---------- Web Push（空 payload，只用 VAPID 認證） ---------- */
async function sendPush(endpoint, env) {
  const r = await fetch(endpoint, {
    method: "POST",
    headers: { TTL: "600", Authorization: "vapid t=" + (await vapid(endpoint, env)) + ", k=" + env.VAPID_PUBLIC },
  });
  return r.status;
}

const tokCache = new Map();
async function vapid(endpoint, env) {
  const origin = new URL(endpoint).origin;
  const now = Math.floor(Date.now() / 1000);
  const c = tokCache.get(origin);
  if (c && c.exp - 120 > now) return c.t;
  const key = await crypto.subtle.importKey("pkcs8", b64d(env.VAPID_PRIVATE),
    { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  const head = b64u(JSON.stringify({ typ: "JWT", alg: "ES256" }));
  const body = b64u(JSON.stringify({ aud: origin, exp: now + 12 * 3600, sub: env.VAPID_SUBJECT }));
  const data = head + "." + body;
  const sig = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, enc(data));
  const t = data + "." + b64u(new Uint8Array(sig));
  tokCache.set(origin, { t, exp: now + 12 * 3600 });
  return t;
}

const enc = (s) => new TextEncoder().encode(s);
function b64u(bytes) {
  const s = typeof bytes === "string" ? bytes : String.fromCharCode(...new Uint8Array(bytes));
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function b64d(s) {
  const b = atob(s.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (s.length % 4) % 4) % 4));
  const a = new Uint8Array(b.length);
  for (let i = 0; i < b.length; i++) a[i] = b.charCodeAt(i);
  return a;
}

export { pick, build, ts2ms, recentVacant };

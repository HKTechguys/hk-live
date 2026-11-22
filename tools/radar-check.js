// 雷達卡回歸檢查:node tools/radar-check.js
// 假 DOM + 真網絡抓 HKO 圖,驗證 6 格載入、兩輪後自動停、可再播、以及「有一格卡住都用已載入嘅格開播」。
const fs = require("fs");
const path = require("path");
const https = require("https");

const ROOT = path.join(__dirname, "..");
const CANDIDATES = [path.join(ROOT, "index.html"), path.join(ROOT, "hk-live.html")];
const PAGE = process.argv[2] || CANDIDATES.find(p => fs.existsSync(p));
if (!PAGE) throw new Error("搵唔到 index.html / hk-live.html");

function extractRadar() {
  const src = fs.readFileSync(PAGE, "utf8");
  const a = src.indexOf("// ---- 雷達雨區");
  const b = src.indexOf("function load(url, fn, tag)");
  if (a < 0 || b < 0) throw new Error("搵唔到雷達段落");
  return src.slice(a, b);
}

const CODE = extractRadar();
const els = {};
function el(id) {
  if (!els[id]) els[id] = {
    id, textContent: "", attrs: {}, style: {}, src: "", innerHTML: "",
    setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener() {}
  };
  return els[id];
}
const document = { getElementById: el, addEventListener() {}, hidden: false };
function pad(n) { return String(n).padStart(2, "0"); }

let hangAt = -1;   // 第幾個圖請求要卡住
let reqNo = 0;
class FakeImage {
  set src(u) {
    this._u = u;
    reqNo++;
    if (reqNo === hangAt) return;                  // 模擬永遠唔回應
    const req = https.get(u, res => {
      res.resume();
      const ok = res.statusCode === 200;
      setTimeout(() => {
        if (ok) this.onload && this.onload();
        else this.onerror && this.onerror();
      }, 25);
    });
    req.on("error", () => setTimeout(() => this.onerror && this.onerror(), 25));
    req.setTimeout(10000, () => req.destroy());
  }
  get src() { return this._u; }
}

const ctx = {};
const fn = new Function("document", "Image", "setTimeout", "setInterval", "clearInterval", "pad", "console",
  CODE + "\nObject.assign(this, {radar: radar, loadRadar, togglePlay, setRange, RAD_N, RAD_STEP});");
fn.call(ctx, document, FakeImage, setTimeout, setInterval, clearInterval, pad, console);

const { radar, loadRadar, togglePlay, RAD_N, RAD_STEP } = ctx;
const cap = () => document.getElementById("radartime").textContent;
const btn = () => document.getElementById("radarplay").textContent;

const wait = ms => new Promise(r => setTimeout(r, ms));
async function until(cond, ms, step = 120) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (cond()) return true;
    await wait(step);
  }
  return cond();
}

const fails = [];
function check(name, ok, detail) {
  console.log((ok ? "PASS " : "FAIL ") + name + (detail ? " — " + detail : ""));
  if (!ok) fails.push(name);
}

(async () => {
  // 1. 六格齊 + 開播
  loadRadar();
  const loaded = await until(() => radar.frames.length >= RAD_N, 20000);
  check("6 格載入", loaded && radar.frames.length === RAD_N, "frames=" + radar.frames.length);
  const started = await until(() => !!radar.timer, 6000);
  check("開始逐格播", started && radar.timer, "cap=" + cap());
  check("格間距 6 分鐘", radar.frames.every((f, i, a) => i === 0 || f.t - a[i - 1].t === RAD_STEP), "step=" + RAD_STEP);

  // 2. 兩輮後自動停
  const stopped = await until(() => !radar.play && !radar.timer, 20000);
  check("兩輮後自動停", stopped, "cap=" + cap());
  check("停喺最新一格", radar.i === radar.frames.length - 1, "i=" + radar.i);
  check("按鈕變播放", btn() === "播放", "btn=" + btn());
  check("停後說明", /按「播放」再播/.test(cap()), cap());

  // 3. 再按播放
  togglePlay();
  const again = await until(() => !!radar.timer, 3000);
  check("可以再播", again && btn() === "暫停", "btn=" + btn() + " cap=" + cap());
  togglePlay();

  // 4. 有一格卡住,仍要用已載入嘅格開播
  await wait(200);
  radar.play = true;                       // 當用戶仍然想播
  reqNo = 0;
  hangAt = 4;
  loadRadar();
  const hung = await until(() => radar.frames.length >= 2 && !!radar.timer, 12000);
  check("卡一格仍然開播", hung, "frames=" + radar.frames.length + " timer=" + !!radar.timer);

  await wait(6000);
  if (radar.timer) togglePlay();
  console.log(fails.length ? "\n" + fails.length + " 項未過: " + fails.join(" / ") : "\n全部通過");
  process.exit(fails.length ? 1 : 0);
})();

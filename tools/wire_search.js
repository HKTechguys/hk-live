  function wireSearch(){
    var q = document.getElementById("q");
    var box = document.getElementById("results");
    var seq = 0, cache = {};

    var pin = null;
    function pinAt(lo, la, label){
      if (pin) { try{ pin.remove(); }catch(e){} }
      pin = new maplibregl.Marker({color:"#22d3ee"}).setLngLat([lo, la])
        .setPopup(new maplibregl.Popup({offset:18, maxWidth:"220px"})
          .setHTML('<div class="pp"><h4>'+esc(label)+'</h4></div>'))
        .addTo(ST.map);
      pin.togglePopup();
    }
    function addHit(h){
      var el = document.createElement("div");
      el.className = "pk-hit";
      el.innerHTML = "<b>"+esc(h.t)+"</b><span>"+esc(h.s)+"</span>";
      el.addEventListener("click", function(){
        if (!ST.map) return;
        if (h.on) { h.on(); applyToggles(); }
        if (h.bounds) flyToTrail(h.bounds);
        else ST.map.flyTo({center:[h.lo,h.la], zoom:h.z, duration:900});
        if (h.pin) pinAt(h.lo, h.la, h.t);
        box.innerHTML = ""; q.blur();
      });
      box.appendChild(el);
    }

    function localHits(v){
      var hits = [];
      ST.parks.forEach(function(p){
        if (((p.n+" "+p.e+" "+p.d+" "+p.a)||"").toLowerCase().indexOf(v) >= 0)
          hits.push({t:p.n, s:p.d+(p.v>=0?" · 空位 "+p.v:" · 無讀數"), la:p.la, lo:p.lo, z:15});
      });
      ST.cafes.forEach(function(c){
        if (((c.n+" "+c.d+" "+c.a)||"").toLowerCase().indexOf(v) >= 0)
          hits.push({t:c.n, s:"Cafe · "+(c.d||"")+(c.h?" · "+c.h:""), la:c.la, lo:c.lo, z:16,
                     on:function(){ TG.cafes = true; setBtn("tg-cafes", true); }});
      });
      ST.meters.forEach(function(m){
        if (m[3] !== 0) return;
        if (((m[4]+" "+m[5])||"").toLowerCase().indexOf(v) >= 0)
          hits.push({t:m[4], s:"空置咪錶位 "+m[0]+" · "+(m[5]||""), la:m[1], lo:m[2], z:17});
      });
      ST.trails.forEach(function(t){
        if (((t.n+" "+t.e+" "+(t.ty||"")+" "+(t.rg||"")+" "+(t.sp||"")+" "+(t.ep||"")+" "+(t.lv||""))||"")
            .toLowerCase().indexOf(v) >= 0)
          hits.push({t:t.n, s:"山徑 · "+t.lv+" · "+t.len+" km", bounds:t.lines, z:14,
                     on:function(){ TG.trails = true; TG.posts = true; setBtn("tg-trails", true); }});
      });
      return hits;
    }

    /* 任何地名／大廈／商場／街道：OSM Photon 地理編碼（開放 CORS，瀏覽器直連） */
    function geoHits(v, cb){
      if (cache[v]) return cb(cache[v]);
      var c = ST.map ? ST.map.getCenter() : {lng:114.17, lat:22.32};
      var url = "https://photon.komoot.io/api/?q=" + encodeURIComponent(q.value.trim())
        + "&limit=6&lang=default&lat=" + c.lat.toFixed(4) + "&lon=" + c.lng.toFixed(4)
        + "&bbox=113.82,22.13,114.45,22.57";
      var ctrl = window.AbortController ? new AbortController() : null, timer = null;
      if (ctrl) timer = setTimeout(function(){ try{ ctrl.abort(); }catch(e){} }, 7000);
      fetch(url, ctrl ? {signal: ctrl.signal} : undefined).then(function(r){ return r.json(); }).then(function(d){
        if (timer) clearTimeout(timer);
        var out = [], seenN = {};
        (d.features || []).forEach(function(f){
          var p = f.properties || {}, co = f.geometry && f.geometry.coordinates;
          if (!co) return;
          var nm = p.name || p.street || "";
          if (!nm) return;
          var hn = p.housenumber && p.housenumber !== "None" ? " " + p.housenumber : "";
          var line = [((p.street || "") + hn).trim(), p.district || p.city || ""].filter(Boolean).join(" · ");
          var key = p.osm_key || "";
          var z = /building|shop|amenity|tourism|office|leisure/.test(key) ? 17
                  : (/landuse|highway|place/.test(key) ? 16 : 14);
          var dk = nm.toLowerCase();
          if (seenN[dk]) return;
          seenN[dk] = 1;
          out.push({t:nm, s:"地名" + (line ? " · " + line : ""), la:co[1], lo:co[0], z:z, pin:true});
        });
        cache[v] = out;
        cb(out);
      }).catch(function(){ if (timer) clearTimeout(timer); cb([]); });
    }

    q.addEventListener("input", function(){
      var v = q.value.trim().toLowerCase();
      box.innerHTML = "";
      seq++;
      if (!v) return;
      var lh = localHits(v);
      lh.slice(0,5).forEach(addHit);
      if (v.length < 2){
        if (!lh.length) box.innerHTML = '<div class="pk-hit"><span>冇匹配結果</span></div>';
        return;
      }
      var my = seq, hint = document.createElement("div");
      hint.className = "pk-hit";
      hint.innerHTML = '<span>搵緊地點…</span>';
      if (!lh.length) box.appendChild(hint);
      setTimeout(function(){
        geoHits(v, function(rs){
          if (my !== seq) return;
          if (hint.parentNode) hint.parentNode.removeChild(hint);
          var names = {};
          lh.forEach(function(h){ names[String(h.t).toLowerCase()] = 1; });
          var extra = rs.filter(function(h){ return !names[String(h.t).toLowerCase()]; });
          if (!extra.length){
            if (!lh.length) box.innerHTML = '<div class="pk-hit"><span>冇匹配結果</span></div>';
            return;
          }
          extra.slice(0,6).forEach(addHit);
        });
      }, 350);
    });
  }

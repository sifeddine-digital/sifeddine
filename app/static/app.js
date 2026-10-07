(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  // ---- recherche dans les listes
  $$("[data-filter]").forEach(function (input) {
    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase();
      $$(input.dataset.filter).forEach(function (li) {
        if (!li.dataset.text) return;
        li.style.display = !q || li.dataset.text.indexOf(q) >= 0 ? "" : "none";
      });
    });
  });

  // ---- copier les accès
  $$("[data-copy]").forEach(function (b) {
    b.addEventListener("click", function () {
      var t = document.getElementById(b.dataset.copy).textContent;
      (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(
        function () { b.textContent = "Copié ✓"; }, function () { window.prompt("Copiez :", t); });
    });
  });

  // ---- cases à cocher groupées
  $$("[data-check-all]").forEach(function (all) {
    var form = all.closest("form");
    var boxes = function () { return $$('input[name="' + all.dataset.checkAll + '"]', form); };
    var count = function () {
      var n = boxes().filter(function (b) { return b.checked; }).length;
      var el = $("#nsel"); if (el) el.textContent = n;
    };
    all.addEventListener("change", function () {
      boxes().forEach(function (b) { if (b.closest("tr").style.display !== "none") b.checked = all.checked; });
      count();
    });
    form.addEventListener("change", count);
  });
  $$("[data-check-group]").forEach(function (g) {
    g.addEventListener("change", function () {
      $$('ul input[type="checkbox"]', g.closest("fieldset")).forEach(function (b) {
        if (b.closest("li").style.display !== "none") b.checked = g.checked;
      });
    });
  });

  // ---- « Tout Oui » d'un bloc
  $$(".all-yes").forEach(function (b) {
    b.addEventListener("click", function () {
      $$('input[type="radio"][value="Oui"]', b.closest("section")).forEach(function (r) {
        if (r.closest(".item").offsetParent !== null) r.checked = true;
      });
      b.closest("form").dispatchEvent(new Event("change", { bubbles: true }));
    });
  });

  // ================================================================ checklist
  var form = $("#ckform");
  if (form) {
    var bar = $("#scorebar");
    var seuilBloc = parseFloat(bar.dataset.seuilBloc), seuilGlobal = parseFloat(bar.dataset.seuilGlobal);
    var key = form.dataset.draftKey;
    var dirty = false;

    var val = function (code) {
      var r = form.querySelector('input[name="r_' + code + '"]:checked');
      return r ? r.value : "";
    };
    var fmt = function (v) { return v === null ? "—" : Math.round(v * 100) + " %"; };
    var cls = function (v) { return v === null ? "" : v >= seuilGlobal ? "ok" : v >= seuilBloc ? "warn" : "crit"; };

    var recompute = function () {
      var tot = 0, oui = 0, non = 0, answered = 0, mins = [], crit = false;
      $$(".bloc", form).forEach(function (sec) {
        var o = 0, n = 0;
        $$(".seg", sec).forEach(function (seg) {
          var r = seg.querySelector("input:checked");
          tot++;
          if (!r) return;
          answered++;
          if (r.value === "Oui") o++;
          if (r.value === "Non") n++;
        });
        var hasNon = n > 0;
        if (sec.dataset.bloc === "elim") { crit = hasNon; return; }
        oui += o; non += n;
        var s = o + n ? o / (o + n) : null;
        if (s !== null) mins.push(s);
        var badge = sec.querySelector("[data-score-for]");
        if (badge) { badge.textContent = fmt(s); badge.className = "bloc-score pill " + cls(s); }
        var obs = sec.querySelector(".obs");
        if (obs) obs.classList.toggle("need", hasNon && !sec.querySelector("textarea[name^=constat_]").value.trim());
        sec.classList.toggle("has-non", hasNon);
      });
      var g = oui + non ? oui / (oui + non) : null;
      var statut = crit ? "Critique" : g === null ? "—" :
        (g < seuilGlobal || Math.min.apply(null, mins) < seuilBloc) ? "À corriger" : "Conforme";
      $("#sc-global").textContent = fmt(g);
      $("#sc-global").className = cls(g);
      $("#sc-count").textContent = answered + "/" + tot;
      var st = $("#sc-statut");
      st.textContent = statut;
      st.className = "pill " + (statut === "Critique" ? "crit" : statut === "À corriger" ? "warn" : statut === "Conforme" ? "ok" : "");
    };

    var saveDraft = function () {
      try {
        var d = {};
        new FormData(form).forEach(function (v, k) { if (k !== "csrf") d[k] = v; });
        localStorage.setItem(key, JSON.stringify({ t: Date.now(), d: d }));
      } catch (e) { /* stockage indisponible */ }
    };
    var restore = function (d) {
      Object.keys(d).forEach(function (k) {
        var el = form.elements[k];
        if (!el) return;
        if (el.length && el[0] && el[0].type === "radio") {
          $$('input[name="' + k + '"]', form).forEach(function (r) { r.checked = r.value === d[k]; });
        } else if (el.type !== "hidden") { el.value = d[k]; }
      });
    };

    // brouillon local non envoyé (perte de réseau, fermeture du navigateur…)
    if (!form.querySelector("fieldset").disabled) {
      try {
        var saved = JSON.parse(localStorage.getItem(key) || "null");
        var hasAnswers = !!form.querySelector('.seg input:checked');
        if (saved && !hasAnswers && Date.now() - saved.t < 14 * 864e5) {
          restore(saved.d);
          var note = document.createElement("div");
          note.className = "flash info";
          note.textContent = "Brouillon local restauré (non encore enregistré sur le serveur).";
          form.parentNode.insertBefore(note, form);
        }
      } catch (e) { /* ignore */ }
    }

    form.addEventListener("change", function () { dirty = true; recompute(); saveDraft(); });
    form.addEventListener("input", function (e) { if (e.target.tagName === "TEXTAREA") { dirty = true; recompute(); saveDraft(); } });

    var prevBtn = $("#copy-prev");
    if (prevBtn) prevBtn.addEventListener("click", function () {
      var prev = JSON.parse(prevBtn.dataset.prev || "{}");
      Object.keys(prev).forEach(function (code) {
        var r = form.querySelector('input[name="r_' + code + '"][value="' + prev[code] + '"]');
        if (r) r.checked = true;
      });
      prevBtn.remove();
      form.dispatchEvent(new Event("change"));
    });

    // position GPS (preuve de présence) — ne bloque jamais l'envoi plus de 4 s
    var sendBtn = $("#send-btn"), located = false;
    if (sendBtn && navigator.geolocation) {
      sendBtn.addEventListener("click", function (e) {
        if (located) return;
        e.preventDefault();
        sendBtn.disabled = true;
        sendBtn.textContent = "Envoi…";
        var go = function () {
          located = true;
          sendBtn.disabled = false;
          var h = document.createElement("input");
          h.type = "hidden"; h.name = "action"; h.value = "envoyer";
          form.appendChild(h);
          dirty = false;
          try { localStorage.removeItem(key); } catch (e) { /* ignore */ }
          form.submit();
        };
        var timer = setTimeout(go, 4000);
        navigator.geolocation.getCurrentPosition(function (p) {
          clearTimeout(timer);
          form.elements.lat.value = p.coords.latitude.toFixed(6);
          form.elements.lng.value = p.coords.longitude.toFixed(6);
          go();
        }, function () { clearTimeout(timer); go(); }, { timeout: 3500, maximumAge: 600000 });
      });
    }
    form.addEventListener("submit", function () { dirty = false; try { localStorage.removeItem(key); } catch (e) { /* ignore */ } });
    window.addEventListener("beforeunload", function (e) { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
    recompute();
  }

  // ================================================================ inventaire
  var inv = $("#invform");
  if (inv) {
    var sync = function () {
      var baie = (inv.querySelector('input[name="baie"]:checked') || {}).value;
      var shsc = (inv.querySelector('input[name="shsc"]:checked') || {}).value;
      $$(".needs-baie", inv).forEach(function (el) { el.hidden = baie !== "Oui"; });
      $$(".needs-shsc", inv).forEach(function (el) { el.hidden = shsc !== "Oui"; });
    };
    inv.addEventListener("change", sync);
    sync();
  }

  // ================================================================ stock
  var stk = $("#stockform");
  if (stk) {
    var calc = function () {
      var p = parseFloat(stk.elements.stock_physique.value), s = parseFloat(stk.elements.stock_systeme.value);
      var out = $("#ecart");
      if (isNaN(p) || isNaN(s) || !s) { out.textContent = "Écart : —"; out.className = "hint"; return; }
      var e = (p - s) / s, ok = Math.abs(e) <= 0.05;
      out.textContent = "Écart : " + (e * 100).toFixed(1) + " % — " + (ok ? "dans la tolérance (≤ 5 %)" : "hors tolérance");
      out.className = "hint " + (ok ? "okc" : "red");
      var r = stk.querySelector('input[name="fiable"][value="' + (ok ? "Oui" : "Non") + '"]');
      if (r && !stk.querySelector('input[name="fiable"]:checked')) r.checked = true;
    };
    stk.addEventListener("input", calc);
    calc();
  }
})();

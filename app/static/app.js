(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  // ---- logo : repli texte si l'image ne charge pas (pas de JS inline : CSP)
  $$("img[data-fallback]").forEach(function (img) {
    var fail = function () { img.parentNode.textContent = img.dataset.fallback; };
    if (img.complete && !img.naturalWidth) fail(); else img.addEventListener("error", fail);
  });

  // ---- listes déroulantes de filtre : envoi automatique
  $$("select[data-autosubmit]").forEach(function (sel) {
    sel.addEventListener("change", function () { sel.form.submit(); });
  });

  // ---- volets ouverts d'office sur grand écran, repliés sur téléphone
  if (window.matchMedia("(min-width: 1000px)").matches) {
    $$("details[data-open-desktop]").forEach(function (d) { d.open = true; });
  }

  // ---- graphique d'évolution : réticule + info-bulle (souris, doigt, clavier)
  $$("[data-chart]").forEach(function (fig) {
    var svg = fig.querySelector("svg"), tip = fig.querySelector(".tip"), cross = fig.querySelector(".cross");
    var show = function (r) {
      var cx = parseFloat(r.dataset.cx);
      cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.setAttribute("visibility", "visible");
      var box = svg.getBoundingClientRect(), scale = box.width / svg.viewBox.baseVal.width;
      tip.innerHTML = "<b>" + r.dataset.week + "</b><i style=\"background:var(--series-1)\"></i>Complétion " + r.dataset.a +
        "<br><i style=\"background:var(--series-2)\"></i>Score moyen " + r.dataset.b;
      tip.hidden = false;
      var x = Math.min(Math.max(cx * scale, 70), box.width - 70);
      tip.style.left = x + "px";
      tip.style.top = "-6px";
    };
    var hide = function () { tip.hidden = true; cross.setAttribute("visibility", "hidden"); };
    $$(".hit", svg).forEach(function (r) {
      r.addEventListener("mouseenter", function () { show(r); });
      r.addEventListener("focus", function () { show(r); });
      r.addEventListener("touchstart", function () { show(r); }, { passive: true });
      r.addEventListener("blur", hide);
    });
    svg.addEventListener("mouseleave", hide);
  });

  // ---- export : options selon le mode choisi
  var ef = $("#exportform");
  if (ef) {
    var syncMode = function () {
      var m = ef.querySelector('input[name="mode"]:checked').value;
      $$(".mode-opt", ef).forEach(function (el) {
        var on = el.dataset.for.split(" ").indexOf(m) >= 0;
        el.hidden = !on;
        $$("select", el).forEach(function (s) { s.disabled = !on; });
      });
    };
    ef.addEventListener("change", syncMode);
    syncMode();
  }

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

  // ---- filtre À faire / Envoyées (liste de la semaine)
  var fc = $("#filterchips");
  if (fc) fc.addEventListener("click", function (e) {
    var b = e.target.closest("button");
    if (!b) return;
    $$("button", fc).forEach(function (x) { x.classList.toggle("on", x === b); });
    $$(".station-list li[data-state]").forEach(function (li) {
      li.hidden = b.dataset.show !== "all" && li.dataset.state !== b.dataset.show;
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
        var chip = document.querySelector('[data-chip="' + sec.dataset.bloc + '"]');
        var segs = sec.querySelectorAll(".seg").length, done = sec.querySelectorAll(".seg input:checked").length;
        if (chip) chip.className = hasNon ? "non" : done === segs ? "done" : done ? "part" : "";
        if (sec.dataset.bloc === "elim") { crit = hasNon; sec.classList.toggle("has-non", hasNon); return; }
        oui += o; non += n;
        var s = o + n ? o / (o + n) : null;
        if (s !== null) mins.push(s);
        var badge = sec.querySelector("[data-score-for]");
        if (badge) { badge.textContent = fmt(s); badge.className = "bloc-score pill " + cls(s); }
        var obs = sec.querySelector(".obs");
        if (obs) {
          obs.classList.toggle("need", hasNon && !sec.querySelector("textarea[name^=constat_]").value.trim());
          if (hasNon) obs.classList.add("open");
          var opener = sec.querySelector(".obs-open");
          if (opener) opener.hidden = obs.classList.contains("open");
        }
        sec.classList.toggle("has-non", hasNon);
      });
      var g = oui + non ? oui / (oui + non) : null;
      var statut = crit ? "Critique" : g === null ? "—" :
        (g < seuilGlobal || Math.min.apply(null, mins) < seuilBloc) ? "À corriger" : "Conforme";
      $("#sc-global").textContent = fmt(g);
      $("#sc-global").className = cls(g);
      $("#sc-count").textContent = answered + "/" + tot + " réponses";
      $("#sc-bar").style.width = (tot ? answered / tot * 100 : 0) + "%";
      var send = $("#send-btn");
      if (send && !send.disabled) {
        send.textContent = answered < tot ? "Envoyer · reste " + (tot - answered) : "Envoyer ✓";
        send.classList.toggle("ready", answered === tot);
      }
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
    // un clic = réponse puis défilement vers le point suivant sans réponse
    form.addEventListener("change", function (e) {
      var t = e.target;
      if (t.type !== "radio" || !t.closest(".seg") || t.dataset.seen) return;
      $$('input[name="' + t.name + '"]', form).forEach(function (r) { r.dataset.seen = "1"; });
      if (t.value === "Non") return;  // laisser le temps d'écrire le constat
      var items = $$(".item", form), i = items.indexOf(t.closest(".item"));
      for (var j = i + 1; j < items.length; j++) {
        if (!items[j].querySelector(".seg input:checked")) {
          var y = items[j].getBoundingClientRect().top + window.scrollY - window.innerHeight * 0.35;
          window.scrollTo({ top: y, behavior: "smooth" });
          break;
        }
      }
    });
    $$(".seg input:checked", form).forEach(function (r) {
      $$('input[name="' + r.name + '"]', form).forEach(function (x) { x.dataset.seen = "1"; });
    });
    $$(".obs-open", form).forEach(function (b) {
      b.addEventListener("click", function () {
        var obs = b.parentNode.querySelector(".obs");
        obs.classList.add("open");
        b.hidden = true;
        obs.querySelector("textarea").focus();
      });
    });
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

/* GOAT Volleyball: a small single-page site. No build step, no libraries.
   Pages: #/ (home), #/matches, #/upcoming, #/standings, #/teams, #/war,
          #/cards, #/players (+ serving, defense), #/about                   */
(function () {
  "use strict";

  var main = document.getElementById("main");
  var tip = document.getElementById("tip");
  var cache = {};
  var meta = null;
  var state = { season: null, tables: {} };

  // ------------------------------------------------------------ helpers --
  function el(tag, attrs, kids) {
    var n = document.createElementNS(
      /^(svg|path|circle|line|rect|g|text|polyline)$/.test(tag) ? "http://www.w3.org/2000/svg" : "http://www.w3.org/1999/xhtml", tag);
    for (var k in attrs || {}) {
      if (attrs[k] == null || attrs[k] === false) continue;
      if (k === "text") n.textContent = attrs[k];
      else if (k === "html") n.innerHTML = attrs[k];
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), attrs[k]);
      else n.setAttribute(k, attrs[k] === true ? "" : attrs[k]);
    }
    (kids || []).forEach(function (c) { if (c != null) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  // Big tables are stored as column names plus rows; turn them back into objects.
  function expand(doc) {
    if (!doc || !doc.cols || !doc.rows) return doc;
    return doc.rows.map(function (r) { var o = {}; doc.cols.forEach(function (c, i) { o[c] = r[i]; }); return o; });
  }
  function load(name) {
    if (cache[name]) return cache[name];
    var inline = window.__DATA__ && window.__DATA__[name];
    cache[name] = (inline !== undefined ? Promise.resolve(inline)
      : fetch("data/" + name + ".json", { cache: "no-cache" })
          .then(function (r) { if (!r.ok) throw new Error(name + " " + r.status); return r.json(); })).then(expand);
    cache[name].catch(function () { delete cache[name]; });
    return cache[name];
  }

  var MINUS = "−";
  var F = {
    int: function (v) { return v == null ? "" : Math.round(v).toLocaleString("en-US"); },
    d1: function (v) { return v == null ? "" : v.toFixed(1).replace("-", MINUS); },
    d2: function (v) { return v == null ? "" : v.toFixed(2).replace("-", MINUS); },
    pct: function (v) { return v == null ? "" : v.toFixed(1); },
    hit: function (v) { return v == null ? "" : (v < 0 ? MINUS : "") + Math.abs(v).toFixed(3).replace(/^0/, ""); },
    s1: function (v) { return v == null ? "" : (v > 0 ? "+" : "") + v.toFixed(1).replace("-", MINUS); },
    s2: function (v) { return v == null ? "" : (v > 0 ? "+" : "") + v.toFixed(2).replace("-", MINUS); },
    txt: function (v) { return v == null ? "" : String(v); }
  };
  function niceDate(iso, withYear) {
    if (!iso) return "";
    var p = iso.split("-"), m = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][+p[1] - 1];
    return m + " " + (+p[2]) + (withYear ? ", " + p[0] : "");
  }
  function seasonInfo(id) { return meta.seasons.filter(function (s) { return s.id === id; })[0]; }
  function confName(id) { return (meta.conferences || {})[id] || id || ""; }

  // ------------------------------------------------------------ tooltip --
  function showTip(html, x, y) {
    tip.innerHTML = html; tip.hidden = false;
    var w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.max(6, Math.min(window.innerWidth - w - 6, x + 12)) + "px";
    tip.style.top = (y + h + 24 > window.innerHeight ? y - h - 10 : y + 14) + "px";
  }
  function hideTip() { tip.hidden = true; }

  // ------------------------------------------------------- column specs --
  // key, header, plain-English meaning, formatter, options
  var WHO = [
    ["name", "Player", "", F.txt, { name: 1, link: 1 }],
    ["team", "Team", "", F.txt, { left: 1 }],
    ["pos", "Pos", "S = setter, OH = outside or opposite hitter, MB = middle blocker, L/DS = libero or defensive specialist", F.txt, { left: 1 }],
    ["mp", "MP", "Matches played", F.int],
    ["sp", "SP", "Sets played", F.int]
  ];
  var COLS = {
    war: WHO.concat([
      ["war", "WAR", "Wins above replacement: the extra match wins she gave her team compared with a bench player in the same number of sets", F.d2, { grp: 1, bar: 1 }],
      ["war100", "WAR/100", "WAR per 100 sets played, about one full season for a starter", F.d2, { sign: 1 }],
      ["att", "Attack", "Points from hitting: kills minus errors, compared with an average player at her position on the same number of swings", F.s1, { grp: 1, sign: 1 }],
      ["srv", "Serve", "Points from serving: aces minus service errors, compared with average on the same number of serves", F.s1, { sign: 1 }],
      ["rec", "Receive", "Points from serve receive: reception errors avoided, compared with average on the same number of receptions", F.s1, { sign: 1 }],
      ["blk", "Block", "Her share of the team's blocks beyond what an average team gets against the same number of opposing swings", F.s1, { sign: 1 }],
      ["dig", "Dig", "Her share of the team's digs beyond what an average team gets on the same number of opposing attacks, at half a point each", F.s1, { sign: 1 }],
      ["set", "Set", "For setters, a quarter of what her hitters did with her sets; for everyone, ball-handling errors", F.s1, { sign: 1 }],
      ["sched", "Schedule", "Points added or taken away for the strength of the opponents faced", F.s1, { grp: 1, sign: 1 }],
      ["paa", "PAA", "Points above average: the six parts plus the schedule adjustment", F.s1, { sign: 1 }],
      ["par", "PAR", "Points above replacement: PAA plus what a bench player would have cost in the same sets", F.s1, { sign: 1 }]
    ]),
    players: WHO.concat([
      ["k", "K", "Kills", F.int, { grp: 1 }],
      ["e", "E", "Attack errors, including attacks that were blocked", F.int],
      ["ta", "TA", "Total attack attempts (swings)", F.int],
      ["hit", "Hit%", "Hitting efficiency: kills minus errors, divided by swings", F.hit, { bar: 0.0001 }],
      ["k_set", "K/S", "Kills per set", F.d2],
      ["kill_pct", "Kill%", "Share of swings that were kills", F.pct, { grp: 1 }],
      ["err_pct", "Err%", "Share of swings that were errors", F.pct],
      ["blocked", "Blkd", "Swings that were blocked for a point, from the play-by-play (not every match has it)", F.int],
      ["so_share", "SO K%", "Share of her kills that came with her team receiving serve. Lower means more of her kills came in transition, with her own team serving", F.pct],
      ["pts", "PTS", "Points: kills plus aces plus solo blocks plus half of each block assist", F.d1, { grp: 1 }],
      ["pts_set", "PTS/S", "Points per set", F.d2]
    ]),
    serving: WHO.concat([
      ["sa", "SA", "Service aces", F.int, { grp: 1 }],
      ["se", "SE", "Service errors", F.int],
      ["sv", "Serves", "Serve attempts", F.int],
      ["sa_set", "SA/S", "Aces per set", F.d2, { bar: 0.0001 }],
      ["ace_pct", "Ace%", "Aces per 100 serves", F.pct],
      ["se_pct", "SE%", "Service errors per 100 serves", F.pct],
      ["ra", "RA", "Serve reception attempts", F.int, { grp: 1 }],
      ["re", "RE", "Reception errors (aces allowed)", F.int],
      ["re_pct", "RE%", "Reception errors per 100 attempts. Lower is better", F.pct],
      ["ast", "A", "Assists", F.int, { grp: 1 }],
      ["ast_set", "A/S", "Assists per set", F.d2]
    ]),
    defense: WHO.concat([
      ["d", "DIG", "Digs", F.int, { grp: 1 }],
      ["d_set", "D/S", "Digs per set", F.d2, { bar: 0.0001 }],
      ["bs", "BS", "Solo blocks", F.int, { grp: 1 }],
      ["ba", "BA", "Block assists", F.int],
      ["blk", "BLK", "Total blocks: solos plus half of each assist", F.d1],
      ["blk_set", "B/S", "Blocks per set", F.d2]
    ]),
    teams: [
      ["team", "Team", "", F.txt, { name: 1 }],
      ["conf_name", "Conf", "Conference", F.txt, { left: 1 }],
      ["w", "W", "Match wins", F.int],
      ["l", "L", "Match losses", F.int],
      ["rating", "Rating", "Points per set better than an average Division I team, adjusted for opponents and weighted toward recent matches", F.s2, { grp: 1, bar: 1 }],
      ["rank", "Rank", "Rank by rating among Division I teams", F.int, { asc: 1 }],
      ["sos", "SOS", "Strength of schedule: the average rating of the opponents played so far", F.s2, { sign: 1 }],
      ["pt_pct", "Pt%", "Share of all points won", F.pct, { grp: 1, mid: 50 }],
      ["so_pct", "SO%", "Sideout rate: share of points won when the other team serves. From the play-by-play", F.pct],
      ["bp_pct", "Brk%", "Break rate: share of points won on the team's own serve. From the play-by-play", F.pct],
      ["hit", "Hit%", "Hitting efficiency: kills minus errors, divided by swings", F.hit, { grp: 1 }],
      ["opp_hit", "Opp Hit%", "Opponents' hitting efficiency. Lower is better", F.hit],
      ["k_set", "K/S", "Kills per set", F.d2],
      ["ace_pct", "Ace%", "Aces per 100 serves", F.pct, { grp: 1 }],
      ["se_pct", "SE%", "Service errors per 100 serves", F.pct],
      ["re_pct", "RE%", "Reception errors per 100 serve receptions. Lower is better", F.pct],
      ["blk_set", "B/S", "Blocks per set", F.d2, { grp: 1 }],
      ["dig_set", "D/S", "Digs per set", F.d2],
      ["close", "2-pt sets", "Record in sets decided by exactly two points. Mostly luck: it rarely carries over", F.txt, { grp: 1, left: 1 }]
    ],
    matches: [
      ["date", "Date", "", function (v) { return niceDate(v, true); }, { name: 1 }],
      ["away", "Away", "The team listed second. At neutral sites home and away are only labels", F.txt, { left: 1 }],
      ["as", "Sets", "Sets won by the away team", F.int],
      ["home", "Home", "", F.txt, { left: 1, grp: 1 }],
      ["hs", "Sets", "Sets won by the home team", F.int],
      ["scores", "Set scores", "Home score first in each set", F.txt, { left: 1, grp: 1, cls: "setscores" }],
      ["pd", "Home pts", "Home points minus away points over the whole match", F.s1, { bar: 1 }],
      ["p_win", "Winner's chance", "The winner's chance of winning before the match, from the two teams' ratings at the time. Low numbers are upsets", F.int, { grp: 1 }]
    ]
  };
  var PLAYER_TABS = [["players", "Attacking"], ["serving", "Serving and passing"], ["defense", "Blocking and defense"]];
  var POS = [["", "All positions"], ["OH", "Outside and opposite"], ["MB", "Middles"], ["S", "Setters"], ["L/DS", "Liberos and DS"]];
  var PAGES = {
    war: { title: "Wins above replacement", file: "war", sort: "war", needPlayers: 1, lede: "One number for a player's whole box score: how many more matches she was worth than a bench player would have been. It rewards efficiency and adjusts for the schedule.",
      min: { key: "sp", label: "Minimum sets played", steps: [0, 10, 20, 40, 60, 80], share: 0.4 }, search: "name", pos: 1, conf: 1, noun: "players" },
    players: { title: "Players", file: "players", tabs: PLAYER_TABS, sort: "k_set", needPlayers: 1, lede: "Kills, errors and efficiency for every hitter.",
      min: { key: "ta", label: "Minimum swings", steps: [0, 25, 50, 100, 200, 300], share: 0.25 }, search: "name", pos: 1, conf: 1, noun: "players" },
    serving: { title: "Players", nav: "players", file: "players", tabs: PLAYER_TABS, sort: "sa_set", needPlayers: 1, lede: "The first two contacts of every rally: serving, serve receive and setting.",
      min: { key: "sp", label: "Minimum sets played", steps: [0, 10, 20, 40, 60, 80], share: 0.4 }, search: "name", pos: 1, conf: 1, noun: "players" },
    defense: { title: "Players", nav: "players", file: "players", tabs: PLAYER_TABS, sort: "d_set", needPlayers: 1, lede: "Digs and blocks for every player.",
      min: { key: "sp", label: "Minimum sets played", steps: [0, 10, 20, 40, 60, 80], share: 0.4 }, search: "name", pos: 1, conf: 1, noun: "players" },
    teams: { title: "Teams", file: "teams", sort: "rating", lede: "Every Division I team, rated by how it wins and loses points and who it has played.", search: "team", conf: 1, noun: "teams" },
    matches: { title: "Matches", file: "games", tabs: [["matches", "Results"], ["upcoming", "Upcoming"]], sort: "date", lede: "Every finished match, with how likely the result looked beforehand.", search: "_teams", conf: 1, noun: "matches" }
  };

  // -------------------------------------------------------------- pages --
  function seasonSelect(onChange, needPlayers) {
    var list = meta.seasons.filter(function (s) { return !needPlayers || s.players; });
    if (!list.some(function (s) { return s.id === state.season; })) state.season = list.length ? list[0].id : state.season;
    var sel = el("select", { id: "f-season", onchange: function () { state.season = +sel.value; onChange(); } },
      list.map(function (s) { return el("option", { value: s.id, text: s.label, selected: s.id === state.season }); }));
    return el("label", { "class": "field" }, ["Season", sel]);
  }
  function confSelect(st, rows, onChange, id) {
    var seen = {};
    rows.forEach(function (r) { if (r.conf) seen[r.conf] = 1; });
    var opts = Object.keys(seen).map(function (c) { return [c, confName(c)]; }).sort(function (a, b) { return a[1].localeCompare(b[1]); });
    if (st.conf && !seen[st.conf]) st.conf = "";
    var sel = el("select", { id: id || "f-conf", onchange: function () { st.conf = sel.value; onChange(); } },
      [["", "All conferences"]].concat(opts).map(function (o) { return el("option", { value: o[0], text: o[1], selected: o[0] === st.conf }); }));
    return el("label", { "class": "field" }, ["Conference", sel]);
  }
  function tabBar(tabs, current) {
    return el("nav", { "class": "tabs", "aria-label": "Views" }, tabs.map(function (t) {
      return el("a", { href: "#/" + t[0], text: t[1], "aria-current": t[0] === current ? "page" : null });
    }));
  }

  function tablePage(kind) {
    var page = PAGES[kind], cols = COLS[kind];
    var st = state.tables[kind] || (state.tables[kind] = { sort: page.sort, dir: -1, q: "", pos: "", conf: "", min: null });
    main.innerHTML = "";
    main.appendChild(el("h1", { text: page.title }));
    if (page.tabs) main.appendChild(tabBar(page.tabs, kind));
    main.appendChild(el("p", { "class": "lede", text: page.lede }));
    var controls = el("div", { "class": "controls" });
    var holder = el("div");
    main.appendChild(controls); main.appendChild(holder);
    controls.appendChild(seasonSelect(function () { st.min = null; tablePage(kind); }, page.needPlayers));
    holder.appendChild(el("p", { "class": "loading", text: "Loading…" }));
    var info = seasonInfo(state.season);

    load(page.file + "_" + state.season).then(function (rows) {
      if (kind === "matches") rows.forEach(function (r) { r._teams = r.home + " " + r.away; });
      if (kind === "teams") rows.forEach(function (r) { r.conf_name = confName(r.conf); });
      if (page.min) {
        var top = Math.max.apply(null, rows.map(function (r) { return r[page.min.key] || 0; }).concat([0]));
        if (st.min == null) {
          st.min = 0;
          page.min.steps.forEach(function (s) { if (s <= top * (page.min.share || 0.25)) st.min = s; });
        }
        var msel = el("select", { id: "f-min", onchange: function () { st.min = +msel.value; draw(); } },
          page.min.steps.map(function (s) { return el("option", { value: s, text: s === 0 ? "No minimum" : s + "+", selected: s === st.min }); }));
        controls.appendChild(el("label", { "class": "field" }, [page.min.label, msel]));
      }
      if (page.pos) {
        var psel = el("select", { id: "f-pos", onchange: function () { st.pos = psel.value; draw(); } },
          POS.map(function (o) { return el("option", { value: o[0], text: o[1], selected: o[0] === st.pos }); }));
        controls.appendChild(el("label", { "class": "field" }, ["Position", psel]));
      }
      if (page.conf) controls.appendChild(confSelect(st, rows, draw));
      if (page.search) {
        var q = el("input", { type: "search", id: "f-search", value: st.q, placeholder: kind === "matches" || kind === "teams" ? "Team" : "Name or team", oninput: function () { st.q = q.value; draw(); } });
        controls.appendChild(el("label", { "class": "field" }, ["Search", q]));
      }
      function draw() {
        var needle = st.q.trim().toLowerCase();
        var shown = rows.filter(function (r) {
          if (page.min && (r[page.min.key] || 0) < st.min) return false;
          if (page.pos && st.pos && r.pos !== st.pos) return false;
          if (page.conf && st.conf && r.conf !== st.conf) return false;
          if (needle && String(r[page.search] || "").toLowerCase().indexOf(needle) < 0 && String(r.team || "").toLowerCase().indexOf(needle) < 0) return false;
          return true;
        });
        holder.innerHTML = "";
        if (!shown.length) {
          holder.appendChild(el("p", { "class": "empty", text: rows.length ? "No " + page.noun + " match these filters. Lower the minimum or clear the search." : "No matches have been played yet." }));
          return;
        }
        var cap = 1500, extra = shown.length > cap ? " The table shows the first " + cap.toLocaleString("en-US") + " in the current order; narrow the filters to see the rest." : "";
        holder.appendChild(statsTable(cols, shown, st, draw, cap));
        holder.appendChild(el("p", { "class": "note", text: "Showing " + Math.min(cap, shown.length).toLocaleString("en-US") + " of " + rows.length.toLocaleString("en-US") + " " + page.noun +
          (info ? ", through " + niceDate(info.through, true) : "") + "." + extra + " Select a column heading to sort; hover it for what it means." }));
        if (page.needPlayers && info && info.with_box < info.matches) holder.appendChild(el("p", { "class": "note", text: "Box scores are available for " + info.with_box.toLocaleString("en-US") + " of " + info.matches.toLocaleString("en-US") + " matches this season. A player who changed schools appears once for each school." }));
      }
      draw();
    }).catch(function () {
      holder.innerHTML = "";
      holder.appendChild(el("p", { "class": "empty", text: "This table could not be loaded. Reload the page to try again." }));
    });
  }

  function statsTable(cols, rows, st, redraw, cap) {
    var sorted = rows.slice().sort(function (a, b) {
      var x = a[st.sort], y = b[st.sort];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      if (typeof x === "string") return st.dir * x.localeCompare(y);
      return st.dir * (y - x) * -1;
    });
    if (cap) sorted = sorted.slice(0, cap);
    var extent = {};
    cols.forEach(function (c) {
      var o = c[4] || {};
      if (o.bar) {
        var mid = o.bar === 1 ? 0 : o.bar;
        extent[c[0]] = Math.max.apply(null, sorted.map(function (r) { return Math.abs((r[c[0]] == null ? mid : r[c[0]]) - mid); })) || 1;
      }
    });
    var head = el("tr", {}, [el("th", { "class": "rk", scope: "col", text: "#" })].concat(cols.map(function (c) {
      var o = c[4] || {}, active = st.sort === c[0];
      var th = el("th", { scope: "col", "class": (o.name ? "name " : "") + (o.left ? "l " : "") + (o.grp ? "grp" : ""),
        "aria-sort": active ? (st.dir < 0 ? "descending" : "ascending") : null });
      var b = el("button", { type: "button", text: c[1], "aria-label": c[1] + (c[2] ? ": " + c[2] : "") + ". Sort.",
        onclick: function () {
          if (st.sort === c[0]) st.dir = -st.dir; else { st.sort = c[0]; st.dir = ((o.name || o.left) && c[0] !== "date") || o.asc ? 1 : -1; }
          redraw();
        } });
      if (c[2]) {
        b.addEventListener("mouseenter", function (e) { showTip("<b>" + esc(c[1]) + "</b><br>" + esc(c[2]), e.clientX, e.clientY); });
        b.addEventListener("mouseleave", hideTip);
        b.addEventListener("focus", function () { var r = b.getBoundingClientRect(); showTip("<b>" + esc(c[1]) + "</b><br>" + esc(c[2]), r.left, r.bottom - 10); });
        b.addEventListener("blur", hideTip);
      }
      th.appendChild(b);
      return th;
    })));
    var body = el("tbody");
    var html = [];
    sorted.forEach(function (r, i) {
      var tds = '<td class="rk">' + (i + 1) + "</td>";
      cols.forEach(function (c) {
        var o = c[4] || {}, v = r[c[0]], cls = [], inner = esc(c[3](v));
        if (o.name) cls.push("name"); if (o.left) cls.push("l"); if (o.grp) cls.push("grp"); if (o.cls) cls.push(o.cls);
        if (o.link && r.id) inner = '<a href="#/player-' + esc(r.id) + '">' + inner + "</a>";
        if (st.sort === c[0]) cls.push("sorted");
        var mid = o.bar ? (o.bar === 1 ? 0 : o.bar) : (o.mid || 0);
        if ((o.bar === 1 || o.sign || o.mid) && v != null && v !== mid) inner = '<span class="' + (v > mid ? "pos" : "neg") + '">' + inner + "</span>";
        if (o.bar && v != null) {
          var w = Math.min(100, Math.abs(v - mid) / extent[c[0]] * 100).toFixed(0);
          inner += '<span class="bar" aria-hidden="true">' + (v < mid ? '<i class="n" style="width:' + w + '%"></i>' : '<i class="p" style="width:' + w + '%"></i>') + "</span>";
        }
        tds += "<td" + (cls.length ? ' class="' + cls.join(" ") + '"' : "") + ">" + inner + "</td>";
      });
      html.push("<tr>" + tds + "</tr>");
    });
    body.innerHTML = html.join("");
    return el("div", { "class": "tablewrap", tabindex: "0", role: "region", "aria-label": "Stats table, scrolls sideways" },
      [el("table", { "class": "stats" }, [el("thead", {}, [head]), body])]);
  }

  // --------------------------------------------------------- point flow --
  // Each set is a string with one character per point: the letter says how the
  // point ended, and it is upper case when the home team won it.
  var ENDING = { k: "Kill", a: "Service ace", b: "Block", e: "Opponent error", s: "Opponent service error" };
  function setPoints(str) {
    var h = 0, a = 0, out = [];
    for (var i = 0; i < str.length; i++) {
      var c = str.charAt(i), home = c === c.toUpperCase();
      if (home) h++; else a++;
      out.push({ h: h, a: a, home: home, how: ENDING[c.toLowerCase()] || "Point" });
    }
    return out;
  }
  function flowSvg(g) {
    var sets = g.sets.map(setPoints);
    var maxLead = 3;
    sets.forEach(function (s) { s.forEach(function (p) { maxLead = Math.max(maxLead, Math.abs(p.h - p.a)); }); });
    var W = 760, H = 250, top = 30, bottom = 22, left = 30, gap = 14;
    var total = sets.reduce(function (n, s) { return n + s.length; }, 0);
    var plotW = W - left - 8 - gap * (sets.length - 1), unit = plotW / total;
    var y = function (v) { return top + (H - top - bottom) * (maxLead - v) / (2 * maxLead); };
    var svg = el("svg", { "class": "flow", viewBox: "0 0 " + W + " " + H, role: "img",
      "aria-label": "Point-by-point lead in each set of " + g.away + " at " + g.home + ". Above the middle line " + g.home + " leads; below it " + g.away + " leads." });
    var step = maxLead > 9 ? 4 : 2;
    for (var v = -Math.floor(maxLead / step) * step; v <= maxLead; v += step) {
      svg.appendChild(el("text", { x: left - 6, y: y(v) + 4, "text-anchor": "end", text: v === 0 ? "0" : String(Math.abs(v)) }));
    }
    var x0 = left;
    sets.forEach(function (s, si) {
      var w = s.length * unit, x = function (i) { return x0 + i * unit; };
      var grp = el("g", {});
      for (var v2 = -Math.floor(maxLead / step) * step; v2 <= maxLead; v2 += step) {
        grp.appendChild(el("line", { "class": v2 === 0 ? "zero" : "grid", x1: x0, x2: x0 + w, y1: y(v2), y2: y(v2) }));
      }
      // a stepped line: the lead only changes when a point ends
      var pts = [[x0, y(0)]];
      s.forEach(function (p, i) { pts.push([x(i + 1), y(p.h - p.a - (p.home ? 1 : -1))]); pts.push([x(i + 1), y(p.h - p.a)]); });
      var d = pts.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" ");
      var clipH = "ch" + g.id + "_" + si, clipA = "ca" + g.id + "_" + si;
      var defs = el("g", {});
      defs.innerHTML = '<clipPath id="' + clipH + '"><rect x="' + x0 + '" y="' + top + '" width="' + w + '" height="' + (y(0) - top) + '"/></clipPath>' +
        '<clipPath id="' + clipA + '"><rect x="' + x0 + '" y="' + y(0) + '" width="' + w + '" height="' + (H - bottom - y(0)) + '"/></clipPath>';
      grp.appendChild(defs);
      var area = "M" + x0 + "," + y(0) + " L" + d.replace(/ /g, " L") + " L" + (x0 + w).toFixed(1) + "," + y(0) + " Z";
      grp.appendChild(el("path", { "class": "area h", d: area, "clip-path": "url(#" + clipH + ")" }));
      grp.appendChild(el("path", { "class": "area a", d: area, "clip-path": "url(#" + clipA + ")" }));
      grp.appendChild(el("polyline", { "class": "line", points: d }));
      var last = s[s.length - 1];
      grp.appendChild(el("circle", { "class": "end " + (last.h > last.a ? "h" : "a"), cx: x0 + w, cy: y(last.h - last.a), r: 5 }));
      grp.appendChild(el("text", { "class": "settitle", x: x0 + w / 2, y: 14, "text-anchor": "middle", text: "Set " + (si + 1) + "  " + last.a + "–" + last.h }));
      var cross = el("line", { "class": "cross", y1: top, y2: H - bottom, x1: x0, x2: x0, visibility: "hidden" });
      grp.appendChild(cross);
      var hit = el("rect", { "class": "hit", x: x0, y: top, width: w, height: H - top - bottom });
      function move(e) {
        var box = svg.getBoundingClientRect(), px = (e.clientX - box.left) / box.width * W;
        var i = Math.max(0, Math.min(s.length - 1, Math.floor((px - x0) / unit))), p = s[i];
        cross.setAttribute("x1", x(i + 1)); cross.setAttribute("x2", x(i + 1)); cross.setAttribute("visibility", "visible");
        showTip("<b>Set " + (si + 1) + ": " + esc(g.away) + " " + p.a + ", " + esc(g.home) + " " + p.h + "</b><br>" + esc(p.home ? g.home : g.away) + " point: " + p.how.toLowerCase(), e.clientX, e.clientY);
      }
      hit.addEventListener("mousemove", move);
      hit.addEventListener("mouseleave", function () { cross.setAttribute("visibility", "hidden"); hideTip(); });
      grp.appendChild(hit);
      svg.appendChild(grp);
      x0 += w + gap;
    });
    svg.appendChild(el("text", { x: left - 6, y: top - 6, "text-anchor": "end", text: "Lead" }));
    return svg;
  }

  function scoreCard(g) {
    var tally = { home: { k: 0, a: 0, b: 0, e: 0, rcv: 0, rcvWon: 0 }, away: { k: 0, a: 0, b: 0, e: 0, rcv: 0, rcvWon: 0 } };
    g.sets.forEach(function (str) {
      var prev = null;
      setPoints(str).forEach(function (p, i) {
        var c = str.charAt(i).toLowerCase(), side = p.home ? "home" : "away";
        tally[side][c === "s" ? "e" : c] += 1;
        // the winner of the last point serves, so the other side is receiving
        var server = c === "a" ? side : c === "s" ? (p.home ? "away" : "home") : prev;
        if (server) { var rc = server === "home" ? "away" : "home"; tally[rc].rcv += 1; if (side === rc) tally[rc].rcvWon += 1; }
        prev = side;
      });
    });
    var so = function (t) { return t.rcv ? (100 * t.rcvWon / t.rcv).toFixed(0) + "%" : ""; };
    var card = el("div", { "class": "scorecard" });
    card.appendChild(el("div", { "class": "scoreline" }, [
      el("span", { "class": "t" }, [el("i", { "class": "dot a" }), g.away]), el("span", { "class": "s", text: String(g.as) }),
      el("span", { "class": "t" }, [el("i", { "class": "dot h" }), g.home]), el("span", { "class": "s", text: String(g.hs) })
    ]));
    card.appendChild(el("p", { "class": "note", style: "margin:0", text: niceDate(g.date, true) }));
    var rows = [["Hitting efficiency", F.hit(g.tot.away.hit), F.hit(g.tot.home.hit)],
      ["Sideout rate", so(tally.away), so(tally.home)],
      ["Points from kills", tally.away.k, tally.home.k], ["Points from aces", tally.away.a, tally.home.a],
      ["Points from blocks", tally.away.b, tally.home.b], ["Points from opponent errors", tally.away.e, tally.home.e]];
    var kv = [el("dt", { text: "" }), el("dd", { text: g.away }), el("dd", { text: g.home })];
    rows.forEach(function (r) { kv.push(el("dt", { text: r[0] }), el("dd", { text: String(r[1]) }), el("dd", { text: String(r[2]) })); });
    card.appendChild(el("dl", { "class": "kv" }, kv));
    var lead = [g.lead.away && (g.lead.away.name + " (" + g.away + ") " + g.lead.away.k + " kills"), g.lead.home && (g.lead.home.name + " (" + g.home + ") " + g.lead.home.k + " kills")].filter(Boolean);
    if (lead.length) card.appendChild(el("p", { style: "margin:0", text: "Kill leaders: " + lead.join("; ") + "." }));
    if (g.p_home != null) {
      var homeWon = g.hs > g.as, pw = Math.round(100 * (homeWon ? g.p_home : 1 - g.p_home));
      card.appendChild(el("p", { "class": "note", style: "margin:0", text: "Before the match the ratings gave " + (homeWon ? g.home : g.away) + " a " + pw + "% chance." + (pw < 35 ? " An upset." : "") }));
    }
    return card;
  }

  // ------------------------------------------------- standings and odds --
  var ODDS_COLS = [
    ["team", "Team", "", F.txt, { name: 1 }],
    ["conf_name", "Conf", "Conference", F.txt, { left: 1 }],
    ["w", "W", "Match wins so far", F.int],
    ["l", "L", "Match losses so far", F.int],
    ["conf_rec", "Conf", "Conference record so far", F.txt, { left: 1 }],
    ["rating", "Rating", "Points per set better than an average Division I team", F.s2, { grp: 1, sign: 1 }],
    ["rank", "Rank", "Rank by rating among Division I teams", F.int, { asc: 1 }],
    ["strength", "Strength", "Chance of beating an average Division I team on a neutral court, in percent", F.pct, { mid: 50 }],
    ["proj_w", "Proj W", "Average regular-season wins across the simulated seasons", F.d1, { grp: 1 }],
    ["proj_l", "Proj L", "Average regular-season losses across the simulated seasons", F.d1],
    ["range", "Likely wins", "Eight simulated seasons in ten finish inside this range", F.txt, { left: 1 }],
    ["proj_conf", "Proj conf", "Average final conference record across the simulated seasons", F.txt, { grp: 1, left: 1 }],
    ["title", "Win conf", "Chance of finishing with the best regular-season conference record, in percent. Ties are shared", F.pct, { bar: 0.0001 }]
  ];
  function oddsPage() {
    var st = state.odds || (state.odds = { sort: "rating", dir: -1, conf: "", q: "" });
    main.innerHTML = "";
    main.appendChild(el("h1", { text: "Projected standings" }));
    main.appendChild(el("p", { "class": "lede", text: "Where every team is headed. The rest of the regular season is played out thousands of times using each team's current rating; the numbers are how often each thing happened." }));
    var controls = el("div", { "class": "controls" }), holder = el("div");
    main.appendChild(controls); main.appendChild(holder);
    holder.appendChild(el("p", { "class": "loading", text: "Loading…" }));
    load("odds").then(function (o) {
      var rows = o.teams.map(function (r) { var c = {}; for (var k in r) c[k] = r[k];
        c.conf_name = confName(r.conf); c.conf_rec = r.cw + "–" + r.cl; c.range = r.w_lo + " to " + r.w_hi;
        c.proj_conf = r.proj_cw.toFixed(1) + "–" + r.proj_cl.toFixed(1); return c; });
      controls.appendChild(confSelect(st, rows, function () { st.sort = st.conf ? "title" : "rating"; st.dir = -1; draw(); }, "f-odds-conf"));
      var q = el("input", { type: "search", id: "f-odds-search", value: st.q, placeholder: "Team", oninput: function () { st.q = q.value; draw(); } });
      controls.appendChild(el("label", { "class": "field" }, ["Search", q]));
      function draw() {
        holder.innerHTML = "";
        var needle = st.q.trim().toLowerCase();
        var shown = rows.filter(function (r) { return (!st.conf || r.conf === st.conf) && (!needle || r.team.toLowerCase().indexOf(needle) >= 0); });
        if (!shown.length) { holder.appendChild(el("p", { "class": "empty", text: "No teams match. Clear the search." })); return; }
        holder.appendChild(statsTable(ODDS_COLS, shown, st, draw));
        holder.appendChild(el("p", { "class": "note", text: o.season + " season, " + o.games_left.toLocaleString("en-US") + " regular-season matches left, " + o.sims.toLocaleString("en-US") +
          " simulated seasons. Conference tournaments and the NCAA tournament are not simulated. The model knows results, not rosters: an injury or a returning starter only shows up once the scores change." }));
      }
      draw();
    }).catch(function () {
      holder.innerHTML = "";
      holder.appendChild(el("p", { "class": "empty", text: "Projections are not available yet. Check back after tonight's update." }));
    });
  }

  function gameDay(iso) {
    var d = new Date(iso + "T12:00:00");
    return isNaN(d) ? iso : d.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
  }
  function upcomingPage() {
    var st = state.upcoming || (state.upcoming = { conf: "", q: "", top: true });
    main.innerHTML = "";
    main.appendChild(el("h1", { text: "Matches" }));
    main.appendChild(tabBar(PAGES.matches.tabs, "upcoming"));
    main.appendChild(el("p", { "class": "lede", text: "The next week of matches with each team's chance of winning." }));
    var controls = el("div", { "class": "controls" }), holder = el("div", { "class": "fixtures" });
    main.appendChild(controls); main.appendChild(holder);
    holder.appendChild(el("p", { "class": "loading", text: "Loading…" }));
    load("odds").then(function (o) {
      var rank = {};
      o.teams.forEach(function (t) { rank[t.id] = t.rank; });
      var all = o.upcoming.map(function (g) { var c = {}; for (var k in g) c[k] = g[k]; c.best = Math.min(rank[g.home_id] || 999, rank[g.away_id] || 999); return c; });
      var seg = el("div", { "class": "seg", role: "group", "aria-label": "Which matches" }, [[true, "Top 50 teams"], [false, "All matches"]].map(function (x) {
        return el("button", { type: "button", "aria-pressed": String(st.top === x[0]), text: x[1], onclick: function () { st.top = x[0]; upcomingPage(); } });
      }));
      controls.appendChild(seg);
      controls.appendChild(confSelect(st, all.map(function (g) { return { conf: g.conf }; }), draw, "f-up-conf"));
      var q = el("input", { type: "search", id: "f-up-search", value: st.q, placeholder: "Team", oninput: function () { st.q = q.value; draw(); } });
      controls.appendChild(el("label", { "class": "field" }, ["Search", q]));
      function draw() {
        holder.innerHTML = "";
        var needle = st.q.trim().toLowerCase();
        var list = all.filter(function (g) {
          if (needle) return (g.home + " " + g.away).toLowerCase().indexOf(needle) >= 0;
          if (st.conf) return g.conf === st.conf;
          return !st.top || g.best <= 50;
        });
        if (!list.length) { holder.appendChild(el("p", { "class": "empty", text: all.length ? "No matches fit these filters in the next week." : "No matches are scheduled in the next week." })); return; }
        var day = null, box = null;
        list.forEach(function (g) {
          if (g.date !== day) { day = g.date; holder.appendChild(el("h2", { text: gameDay(g.date) })); box = el("div", { "class": "fixlist" }); holder.appendChild(box); }
          var ph = Math.round(g.p_home * 100), pa = 100 - ph, t = g.start ? new Date(g.start * 1000) : null;
          var tag = function (id) { return rank[id] && rank[id] <= 25 ? "#" + rank[id] + " " : ""; };
          box.appendChild(el("div", { "class": "fixture" }, [
            el("span", { "class": "ftime", text: t && !isNaN(t) ? t.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }) : "" }),
            el("span", { "class": "fteam away" + (pa > ph ? " fav" : ""), text: tag(g.away_id) + g.away }),
            el("b", { "class": "fpct", text: pa + "%" }),
            el("span", { "class": "fbar", role: "img", "aria-label": g.away + " " + pa + "%, " + g.home + " " + ph + "%" }, [
              el("i", { "class": "a", style: "width:" + pa + "%" }), el("i", { "class": "h", style: "width:" + ph + "%" })]),
            el("b", { "class": "fpct", text: ph + "%" }),
            el("span", { "class": "fteam home" + (ph > pa ? " fav" : ""), text: tag(g.home_id) + g.home }),
            el("span", { "class": "fnote", text: g.conf ? confName(g.conf) : "" })
          ]));
        });
        var m = o.model || {};
        holder.appendChild(el("p", { "class": "note", text: "Away team on the left, home team on the right; a number before a name is the team's rank by rating. " +
          (m.accuracy ? "Tested on " + m.matches.toLocaleString("en-US") + " past matches it had not seen, the favorite won " + Math.round(m.accuracy * 100) + "% of the time." : "") }));
      }
      draw();
    }).catch(function () {
      holder.innerHTML = "";
      holder.appendChild(el("p", { "class": "empty", text: "Upcoming matches are not available yet. Check back after tonight's update." }));
    });
  }

  // ------------------------------------------------------ player cards --
  var CARD_ROWS = [
    ["Value, in points per 100 sets", [
      ["war", "WAR", "everything below added up, with the schedule adjustment, in wins per 100 sets"],
      ["att", "Attack", "kills minus errors against an average player at her position on the same swings"],
      ["srv", "Serve", "aces minus errors against average on the same serves"],
      ["rec", "Serve receive", "reception errors avoided against average on the same receptions"],
      ["blk", "Block", "her share of the team's blocks beyond average for the swings it faced"],
      ["dig", "Dig", "her share of the team's digs beyond average for the attacks it faced"],
      ["set", "Setting", "a quarter of what her hitters did with her sets"]]],
    ["Box score", [
      ["k_set", "Kills per set", "kills per set played"],
      ["hit", "Hitting efficiency", "kills minus errors, divided by swings"],
      ["ace_set", "Aces per set", "service aces per set played"],
      ["d_set", "Digs per set", "digs per set played"],
      ["blk_set", "Blocks per set", "solo blocks plus half of each assist, per set"],
      ["ast_set", "Assists per set", "assists per set played"],
      ["re_pct", "Reception errors", "errors per 100 serve receptions; fewer is better, so a high bar means few errors"]]]
  ];
  var POS_WORD = { "S": "setters", "OH": "outside and opposite hitters", "MB": "middle blockers", "L/DS": "liberos and defensive specialists" };
  var POS_ONE = { "S": "Setter", "OH": "Outside or opposite hitter", "MB": "Middle blocker", "L/DS": "Libero or defensive specialist" };
  function cardValue(key, v) {
    if (v == null) return "";
    if (key === "hit") return F.hit(v);
    if (key === "re_pct") return v.toFixed(1) + " per 100";
    if (key === "war") return F.s2(v) + " wins per 100 sets";
    if (/_set$/.test(key)) return v.toFixed(2);
    return F.s1(v) + " points per 100 sets";
  }
  function ordinal(n) { var s = ["th", "st", "nd", "rd"], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); }

  function cardPage(wanted) {
    main.innerHTML = "";
    main.appendChild(el("h1", { text: "Player cards" }));
    main.appendChild(el("p", { "class": "lede", text: "Where a player ranks at her position in each part of the game. A bar at 90 means she was better than 90% of regulars at that position." }));
    var controls = el("div", { "class": "controls" }), holder = el("div");
    main.appendChild(controls); main.appendChild(holder);
    holder.appendChild(el("p", { "class": "loading", text: "Loading…" }));
    var cs = state.card || (state.card = { id: null, season: null });

    load("player_index").then(function (index) {
      var byId = {};
      index.forEach(function (p) { byId[p.id] = p; });
      if (wanted && byId[wanted]) { if (cs.id !== wanted) cs.season = null; cs.id = wanted; }
      if (!cs.id || !byId[cs.id]) {      // start on the most valuable player of the newest season
        var newest = Math.max.apply(null, index.map(function (p) { return p.season; })), best = null;
        index.forEach(function (p) { if (p.season === newest && (!best || (p.war || 0) > (best.war || 0))) best = p; });
        cs.id = best ? best.id : (index[0] && index[0].id);
      }
      var box = el("input", { type: "search", id: "f-card-search", placeholder: "Type a name", autocomplete: "off" });
      var hits = el("div", { "class": "hits", role: "listbox" });
      box.addEventListener("input", function () {
        var q = box.value.trim().toLowerCase(); hits.innerHTML = "";
        if (q.length < 2) return;
        index.filter(function (p) { return (p.name || "").toLowerCase().indexOf(q) >= 0; })
          .sort(function (a, b) { return b.season - a.season || (b.war || 0) - (a.war || 0); })
          .slice(0, 8).forEach(function (p) {
            hits.appendChild(el("a", { href: "#/player-" + p.id, role: "option", text: p.name + ", " + p.pos + ", " + p.team }));
          });
        if (!hits.children.length) hits.appendChild(el("span", { text: "No player by that name in these seasons." }));
      });
      controls.appendChild(el("label", { "class": "field search" }, ["Find a player", box, hits]));
      if (!cs.id) { holder.innerHTML = ""; holder.appendChild(el("p", { "class": "empty", text: "No player cards yet." })); return; }

      var teamId = cs.id.split("~")[0], bucket = 0;
      for (var ci = 0; ci < teamId.length; ci++) bucket += teamId.charCodeAt(ci);   // same rule as the pipeline
      return load("cards/b" + (bucket % 48)).then(function (file) {
        var doc = file.teams[teamId]; doc.metrics = file.metrics;
        var pl = doc.players[cs.id], years = Object.keys(pl.y).sort();
        if (!cs.season || !pl.y[cs.season]) cs.season = years[years.length - 1];
        var y = pl.y[cs.season], metrics = doc.metrics, group = POS_WORD[y.p] || "players";
        var ysel = el("select", { id: "f-card-season", onchange: function () { cs.season = ysel.value; cardPage(cs.id); } },
          years.slice().reverse().map(function (s) { return el("option", { value: s, text: s, selected: s === cs.season }); }));
        controls.appendChild(el("label", { "class": "field" }, ["Season", ysel]));

        holder.innerHTML = "";
        var card = el("article", { "class": "pcard" });
        var warPct = y.pc[0];
        card.appendChild(el("header", { "class": "pcard-head" }, [
          el("div", {}, [el("h2", { text: pl.n }),
            el("p", { text: (POS_ONE[y.p] || "Player") + ", " + doc.team + (y.conf ? " (" + confName(y.conf) + ")" : "") + ". " + cs.season + " season." }),
            el("p", { "class": "pcard-bio", text: y.mp + " matches, " + y.sp + " sets. " + F.d2(y.war) + " WAR." })]),
          el("div", { "class": "pcard-war" }, [el("b", { text: warPct == null ? "–" : String(warPct) }),
            el("span", { text: warPct == null ? "Not enough sets to rank" : "WAR percentile among " + group })])
        ]));
        var body = el("div", { "class": "pcard-body" });
        CARD_ROWS.forEach(function (g) {
          var sec = el("section", {}, [el("h3", { text: g[0] })]);
          g[1].forEach(function (m) {
            var j = metrics.indexOf(m[0]), p = y.pc[j], v = y.v[j];
            if (p == null && (m[0] === "set" || m[0] === "ast_set") && y.p !== "S") return;
            var row = el("div", { "class": "prow", tabindex: "0" });
            row.appendChild(el("span", { "class": "plabel", text: m[1] }));
            var track = el("span", { "class": "ptrack", role: "img", "aria-label": p == null ? m[1] + ": not ranked" : m[1] + ": " + ordinal(p) + " percentile" });
            if (p != null) {
              var strength = Math.round(30 + Math.abs(p - 50) * 1.4);
              track.appendChild(el("i", { style: "width:" + Math.max(p, 2) + "%;background:color-mix(in srgb, var(--" + (p >= 50 ? "blue" : "red") + ") " + strength + "%, var(--mid))" }));
            }
            row.appendChild(track);
            row.appendChild(el("b", { "class": "ppct", text: p == null ? "" : String(p) }));
            row.appendChild(el("span", { "class": "pval", text: p == null ? "Not ranked: too few sets or chances" : cardValue(m[0], v) }));
            var tipText = "<b>" + esc(m[1]) + "</b><br>" + esc(m[2].charAt(0).toUpperCase() + m[2].slice(1)) + "." +
              (p == null ? "<br>Not enough of this kind of play to rank her." : "<br>Better than " + p + "% of " + group + " who play regularly.");
            row.addEventListener("mousemove", function (e) { showTip(tipText, e.clientX, e.clientY); });
            row.addEventListener("mouseleave", hideTip);
            row.addEventListener("focus", function () { var r = row.getBoundingClientRect(); showTip(tipText, r.left + 40, r.bottom - 6); });
            row.addEventListener("blur", hideTip);
            sec.appendChild(row);
          });
          body.appendChild(sec);
        });
        card.appendChild(body);
        card.appendChild(el("p", { "class": "pcard-foot", text: "Bars run from 0 (worst) to 100 (best); the tick marks the middle of the position. " + meta.site + "." }));
        holder.appendChild(card);

        holder.appendChild(el("h2", { text: "Season by season", style: "margin-top:32px" }));
        var maxAbs = Math.max.apply(null, years.map(function (s) { return Math.abs(pl.y[s].war || 0); }).concat([1]));
        var cols = [["Season", "l"], ["Pos", "l"], ["MP"], ["SP"], ["K"], ["Hit%"], ["A"], ["SA"], ["DIG"], ["BLK"], ["WAR"], ["", "l"]];
        var tb = el("tbody");
        years.slice().reverse().forEach(function (s) {
          var r = pl.y[s], w = Math.round(Math.abs(r.war || 0) / maxAbs * 100);
          var bar = '<span class="bar wide" aria-hidden="true">' + ((r.war || 0) < 0 ? '<i class="n" style="width:' + w + '%"></i>' : '<i class="p" style="width:' + w + '%"></i>') + "</span>";
          var cells = [r.mp, r.sp, r.k, r.ta ? F.hit((r.k - r.e) / r.ta) : "", r.ast, r.sa, r.d, F.d1(r.blk)];
          var tr = el("tr", { "class": s === cs.season ? "current" : "" });
          tr.innerHTML = '<td class="l"><a href="#/player-' + esc(cs.id) + '">' + s + '</a></td><td class="l">' + esc(r.p) + "</td>" +
            cells.map(function (c) { return "<td>" + esc(c) + "</td>"; }).join("") + "<td><b>" + F.d2(r.war) + '</b></td><td class="l">' + bar + "</td>";
          tr.querySelector("a").addEventListener("click", function (e) { e.preventDefault(); cs.season = s; cardPage(cs.id); });
          tb.appendChild(tr);
        });
        holder.appendChild(el("div", { "class": "tablewrap fit" }, [el("table", { "class": "stats plain" }, [
          el("thead", {}, [el("tr", {}, cols.map(function (c) { return el("th", { scope: "col", "class": c[1] || "", text: c[0] }); }))]), tb])]));
        holder.appendChild(el("p", { "class": "note", text: "Seasons at " + doc.team + " only. A player who changed schools has a separate card for each. Select a season to see its card." }));
        document.title = pl.n + " | " + meta.site;
      });
    }).catch(function () {
      holder.innerHTML = "";
      holder.appendChild(el("p", { "class": "empty", text: "Player cards could not be loaded. Reload the page to try again." }));
    });
  }

  // --------------------------------------------------------------- home --
  function home() {
    main.innerHTML = "";
    var hero = el("section", { "class": "hero" });
    hero.appendChild(el("h1", { text: "Every rally, counted." }));
    hero.appendChild(el("p", { "class": "lede", text: "A 3–1 win can be a rout or four coin flips. The chart follows the lead point by point through each set of a recent match: above the line the home team is ahead, below it the visitors are." }));
    main.appendChild(hero);
    var strip = el("div", { "class": "gamestrip", role: "group", "aria-label": "Recent matches" });
    var grid = el("div", { "class": "rinkgrid" });
    hero.appendChild(strip); hero.appendChild(grid);
    var leaders = el("section", { "class": "leaders", "aria-label": "Season leaders" });
    main.appendChild(leaders);

    load("recent").then(function (games) {
      if (!games.length) { grid.appendChild(el("p", { "class": "empty", text: "No matches with point-by-point data yet this season." })); return; }
      var current = state.game && games.filter(function (g) { return g.id === state.game; })[0] || games[0];
      function pick(g) {
        current = g; state.game = g.id;
        Array.prototype.forEach.call(strip.children, function (b) { b.setAttribute("aria-pressed", String(+b.dataset.id === g.id)); });
        grid.innerHTML = "";
        var box = el("div", { "class": "rinkbox" }, [el("div", { "class": "flowwrap", tabindex: "0", role: "region", "aria-label": "Point-by-point chart, scrolls sideways on small screens" }, [flowSvg(g)])]);
        box.appendChild(el("div", { "class": "legend", html:
          '<span><svg width="14" height="14"><rect x="1" y="1" width="12" height="12" fill="var(--blue-soft)" stroke="var(--blue)"/></svg> ' + esc(g.home) + " ahead</span>" +
          '<span><svg width="14" height="14"><rect x="1" y="1" width="12" height="12" fill="var(--away-soft)" stroke="var(--away)"/></svg> ' + esc(g.away) + " ahead</span>" +
          "<span>Each step is one point. Hover for the score and how the point ended.</span>" }));
        grid.appendChild(box);
        grid.appendChild(scoreCard(g));
      }
      games.forEach(function (g) {
        var hw = g.hs > g.as;
        strip.appendChild(el("button", { type: "button", "class": "gamechip", "data-id": g.id, "aria-pressed": "false",
          "aria-label": g.away + " " + g.as + ", " + g.home + " " + g.hs + ", " + niceDate(g.date), onclick: function () { pick(g); } }, [
          el("span", { "class": "d", text: niceDate(g.date) }),
          el("span", { "class": hw ? "" : "w", text: g.away }), el("span", { "class": "n " + (hw ? "" : "w"), text: String(g.as) }),
          el("span", { "class": hw ? "w" : "", text: g.home }), el("span", { "class": "n " + (hw ? "w" : ""), text: String(g.hs) })
        ]));
      });
      pick(current);
    }).catch(function () { grid.appendChild(el("p", { "class": "empty", text: "The match chart could not be loaded. Reload the page to try again." })); });

    var latest = meta.seasons[0];
    Promise.all([load("teams_" + latest.id).catch(function () { return []; }),
      latest.players ? load("war_" + latest.id).catch(function () { return []; }) : Promise.resolve([]),
      load("odds").catch(function () { return null; })]).then(function (d) {
      function block(title, rows, val, fmt, route, sub, linkText) {
        var ol = el("ol", {}, rows.slice(0, 5).map(function (r, i) {
          return el("li", {}, [el("span", { "class": "rk", text: String(i + 1) }),
            el("span", { "class": "who" }, [r.name || r.team, el("small", { text: r.name ? r.team : confName(r.conf) })]),
            el("span", { "class": "val", text: fmt(r[val]) })]);
        }));
        return el("div", {}, [el("h2", { text: title }), el("p", { "class": "note", style: "margin:0 0 8px", text: sub }), ol,
          el("p", {}, [el("a", { href: "#/" + route, text: linkText })])]);
      }
      var by = function (rows, k) { return rows.slice().sort(function (a, b) { return (b[k] == null ? -1e9 : b[k]) - (a[k] == null ? -1e9 : a[k]); }); };
      var when = latest.label + ", through " + niceDate(latest.through);
      if (d[0].length) leaders.appendChild(block("Team ratings", by(d[0], "rating"), "rating", F.s2, "teams", "Points per set better than average. " + when, "All teams"));
      if (d[1].length) leaders.appendChild(block("Wins above replacement", by(d[1], "war"), "war", F.d2, "war", when, "Full WAR table"));
      if (d[2] && d[2].teams.length) leaders.appendChild(block("Projected wins", by(d[2].teams, "proj_w"), "proj_w", F.d1, "standings", "Regular season, " + d[2].sims.toLocaleString("en-US") + " simulated seasons", "Projected standings"));
    }).catch(function () {});
  }

  // -------------------------------------------------------------- about --
  function about() {
    main.innerHTML = "";
    var p = el("div", { "class": "prose" });
    main.appendChild(el("h1", { text: "How the numbers work" }));
    main.appendChild(p);
    p.innerHTML =
      "<p class='lede'>A match record says who won. Points say by how much, and against whom. This site is built on points.</p>" +
      "<h2>Team ratings</h2>" +
      "<p>A rating is how many points per set a team is better than an average Division I team. After every match, the point margin per set is compared with what the two ratings predicted, and both teams move toward the result. Beating a strong team by two points a set counts for more than beating a weak one by four.</p>" +
      "<p>Recent matches count more than old ones. Each team starts a season at three quarters of last season's rating, because rosters turn over. The rating does not know who is on the floor: an injury or a transfer only shows up once the scores change.</p>" +
      "<h2>Win probabilities</h2>" +
      "<p>A match's win probability comes from the gap between the two ratings plus an edge for the home team. The edge is measured separately for conference matches and everything else, because early-season tournaments are often on neutral courts where home and away are only labels.</p>" +
      "<p id='ab-pred'></p><div id='ab-chart'></div>" +
      "<p class='note'>If the model is honest, matches it rates at 70% are won by the home team about 70% of the time. Each point is a tenth of the test matches, grouped from the home team's worst chances to its best. Points on the dashed line are perfect.</p>" +
      "<h2>Projected standings</h2>" +
      "<p>The rest of the regular season is played out thousands of times. In each run every team's rating is nudged up or down a little first, because the ratings themselves are estimates. The conference column is the chance of finishing with the best conference record. Conference tournaments and the NCAA tournament are not simulated, so there are no championship odds yet.</p>" +
      "<h2>Wins above replacement</h2>" +
      "<p>WAR turns a player's box score into the match wins she added compared with a bench player. It is built in points first. Attack is kills minus errors, set against what an average player at the same position would do with the same number of swings. Serve and serve receive work the same way, per serve and per reception. Blocks and digs are measured for the team against the number of attacks it faced, then shared out by who made them. A setter gets a quarter of what her hitters did with her sets, and the hitters keep the rest.</p>" +
      "<p id='ab-war'></p>" +
      "<p>What it cannot see matters. The box score has no pass ratings, no record of who served a tough ball that led to an easy point, and no way to tell a great set from a poor one that the hitter rescued. A dig is counted at half a point because it keeps a rally alive without winning it, and that half is a judgment call. Liberos and setters are therefore measured much more roughly than hitters. Treat small gaps as noise.</p>" +
      "<h2>Player cards</h2>" +
      "<p>A card ranks a player against regulars at her position, on rates, so missed matches do not count against her. She is only ranked on a skill she actually performs: a libero is not ranked on hitting, and only setters are ranked on setting.</p>" +
      "<h2>What the play-by-play adds</h2>" +
      "<p>The point-by-point feed says who won each rally and how it ended. The winner of a point serves the next one, which gives each team's sideout rate (points won receiving serve) and break rate (points won serving). The feed does not name the server, and it lists substitutions too loosely to know who is on the court, so there are no serving-run or lineup numbers.</p>" +
      "<div id='ab-cov'></div>" +
      "<h2>What is missing</h2>" +
      "<p>Volleyball has no public equivalent of hockey's shot locations, so there is no expected-points model here. Player seasons are tied to a school: a player who transfers shows up as two players. Box scores before 2022 are empty in the NCAA's feed, so player numbers start in 2022, and 2021 is used only to start the team ratings.</p>" +
      "<h2>Glossary</h2><dl class='gloss' id='ab-gloss'></dl>" +
      "<h2>Data</h2><p>Matches come from the NCAA's public scoreboard, box score and play-by-play feeds and are refreshed every night. Matches from the last three days are re-checked for stat corrections. Every match involving a Division I team is included; ratings for schools outside Division I are rough because they appear only a few times.</p>";
    var seen = {}, gl = document.getElementById("ab-gloss");
    ["teams", "war", "players", "serving", "defense"].reduce(function (acc, k) { return acc.concat(COLS[k].map(function (c) { return [c[1], c[2]]; })); }, []).forEach(function (g) {
      if (!g[1] || seen[g[0]] || /^(W|L|Team|Conf|Player)$/.test(g[0])) return;
      seen[g[0]] = 1; gl.appendChild(el("dt", { text: g[0] })); gl.appendChild(el("dd", { text: g[1] }));
    });
    var cov = document.getElementById("ab-cov");
    var tb = el("tbody");
    meta.seasons.forEach(function (s) {
      var tr = el("tr");
      tr.innerHTML = '<td class="l">' + s.label + "</td><td>" + F.int(s.matches) + "</td><td>" + F.int(s.with_box) + "</td><td>" + F.int(s.with_points) + "</td>";
      tb.appendChild(tr);
    });
    cov.appendChild(el("div", { "class": "tablewrap fit cov" }, [el("table", { "class": "stats plain" }, [
      el("thead", {}, [el("tr", {}, [["Season", "l"], ["Matches"], ["With a box score"], ["With every point"]].map(function (c) { return el("th", { scope: "col", "class": c[1] || "", text: c[0] }); }))]), tb])]));
    cov.appendChild(el("p", { "class": "note", text: "A match counts as having every point only when the parsed points add up to the official score of every set." }));
    var vm = meta.value || {};
    if (vm.points_per_win) {
      var tc = vm.team_check;
      document.getElementById("ab-war").textContent = "The parts are scaled so that a team's players add up to its real point margin, then adjusted for the opponents faced. Replacement level is what bench players across Division I produce per set. Points become wins at about " + Math.round(vm.points_per_win) + " points per win, measured from team results." +
        (tc ? " As a check, adding up each team's player WAR and comparing it with its winning percentage over " + tc.team_seasons + " team-seasons gives a correlation of " + tc.corr_win_pct.toFixed(2) + "." : "");
    }
    load("odds").then(function (o) {
      var m = o.model || {};
      if (!m.matches) { document.getElementById("ab-pred").textContent = "The model has not been tested yet: that needs at least two full seasons of results."; return; }
      document.getElementById("ab-pred").textContent = "Tested on " + m.matches.toLocaleString("en-US") + " matches from seasons the weights were not fitted on, the favorite won " + (100 * m.accuracy).toFixed(1) +
        "% of the time. Always picking the home team wins " + (100 * Math.max(m.home_win_rate, 1 - m.home_win_rate)).toFixed(1) + "%. On log loss, the usual score for probabilities (lower is better), it scored " + m.log_loss.toFixed(3) + " against " + m.baseline_log_loss.toFixed(3) + " for that baseline.";
      if (m.calibration) document.getElementById("ab-chart").appendChild(calibration(m.calibration));
    }).catch(function () {});
  }

  function calibration(bins) {
    var W = 480, H = 320, L = 46, B = 36, T = 10, R = 12;
    var x = function (v) { return L + (W - L - R) * v; }, y = function (v) { return H - B - (H - B - T) * v; };
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Calibration chart: predicted chance against how often the home team won" });
    for (var i = 0; i <= 4; i++) {
      var v = i / 4;
      svg.appendChild(el("line", { "class": "axis", x1: L, x2: W - R, y1: y(v), y2: y(v) }));
      svg.appendChild(el("text", { x: L - 6, y: y(v) + 4, "text-anchor": "end", text: (v * 100).toFixed(0) + "%" }));
      svg.appendChild(el("text", { x: x(v), y: H - B + 16, "text-anchor": "middle", text: (v * 100).toFixed(0) + "%" }));
    }
    svg.appendChild(el("line", { "class": "ideal", x1: x(0), y1: y(0), x2: x(1), y2: y(1) }));
    svg.appendChild(el("polyline", { "class": "ln", points: bins.map(function (b) { return x(b.predicted).toFixed(1) + "," + y(b.actual).toFixed(1); }).join(" ") }));
    bins.forEach(function (b) {
      var c = el("circle", { "class": "pt", cx: x(b.predicted), cy: y(b.actual), r: 4.5, tabindex: "0" });
      var label = "<b>Predicted " + (100 * b.predicted).toFixed(0) + "%</b><br>Home team won " + (100 * b.actual).toFixed(0) + "% of " + b.n.toLocaleString("en-US") + " matches";
      c.addEventListener("mousemove", function (e) { showTip(label, e.clientX, e.clientY); });
      c.addEventListener("mouseleave", hideTip);
      c.addEventListener("focus", function () { var r = c.getBoundingClientRect(); showTip(label, r.right, r.top); });
      c.addEventListener("blur", hideTip);
      svg.appendChild(c);
    });
    svg.appendChild(el("text", { x: (L + W - R) / 2, y: H - 4, "text-anchor": "middle", text: "Home team's predicted chance" }));
    svg.appendChild(el("text", { x: 12, y: (H - B) / 2, "text-anchor": "middle", transform: "rotate(-90 12 " + (H - B) / 2 + ")", text: "How often the home team won" }));
    return el("div", { "class": "chart" }, [svg]);
  }

  // ------------------------------------------------------------- router --
  function route() {
    hideTip();
    var raw = location.hash.replace(/^#\/?/, "").split("?")[0] || "home";
    var pm = /^player-(.+)$/.exec(raw);
    var r = pm ? "cards" : raw.toLowerCase();
    Array.prototype.forEach.call(document.querySelectorAll(".nav a"), function (a) {
      var navKey = r === "upcoming" ? "matches" : (PAGES[r] && PAGES[r].nav) || r;
      if (a.dataset.route === navKey) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    window.scrollTo(0, 0);
    if (r === "cards") { document.title = "Player cards | " + meta.site; cardPage(pm ? decodeURIComponent(pm[1]) : null); return; }
    if (r === "standings") { oddsPage(); document.title = "Projected standings | " + meta.site; return; }
    if (r === "upcoming") { upcomingPage(); document.title = "Upcoming matches | " + meta.site; return; }
    if (PAGES[r]) tablePage(r); else if (r === "about") about(); else home();
    document.title = (r === "war" ? "WAR | " : PAGES[r] ? PAGES[r].title + " | " : r === "about" ? "About | " : "") + meta.site;
  }

  load("meta").then(function (m) {
    meta = m; delete cache.meta;
    state.season = m.seasons[0].id;
    document.getElementById("brand-name").textContent = m.site;
    var d = new Date(m.updated_utc);
    document.getElementById("foot-updated").textContent = "Updated " + (isNaN(d) ? m.updated_utc : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })) + ".";
    window.addEventListener("hashchange", route);
    route();
  }).catch(function () {
    main.innerHTML = "";
    main.appendChild(el("p", { "class": "empty", text: "The stats have not been published yet. Check back after tonight's update." }));
  });
})();

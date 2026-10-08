/* GOAT Volleyball: one page, no libraries. Lists the matches of the 25 ranked teams. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var data = null, state = { week: null, team: null };

  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    for (var k in attrs || {}) {
      if (attrs[k] == null || attrs[k] === false) continue;
      if (k === "text") n.textContent = attrs[k];
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), attrs[k]);
      else n.setAttribute(k, attrs[k] === true ? "" : attrs[k]);
    }
    (kids || []).forEach(function (c) { if (c != null) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }

  // ---- dates. A day is "YYYY-MM-DD"; weeks run Monday to Sunday, like the poll. ----
  function iso(d) { return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2); }
  function day(s) { var p = s.split("-"); return new Date(+p[0], +p[1] - 1, +p[2], 12); }
  function addDays(s, n) { var d = day(s); d.setDate(d.getDate() + n); return iso(d); }
  function monday(s) { var d = day(s); return addDays(s, -((d.getDay() + 6) % 7)); }
  function short(s) { return day(s).toLocaleDateString(undefined, { month: "short", day: "numeric" }); }
  function long(s) { return day(s).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }); }
  var today = iso(new Date());

  // A team's logo, served by ncaa.com: one drawing for light pages, one for dark.
  function logo(teamId, cls) {
    if (!data.logo || !teamId) return null;
    var url = function (theme) { return data.logo.replace("{theme}", theme).replace("{team}", encodeURIComponent(teamId)); };
    var img = el("img", { src: url("bgl"), alt: "", loading: "lazy", decoding: "async" });
    var pic = el("picture", { "class": "logo " + (cls || "") }, [el("source", { srcset: url("bgd"), media: "(prefers-color-scheme: dark)" }), img]);
    img.addEventListener("error", function () { pic.style.visibility = "hidden"; });   // no logo for this school: leave the space
    return pic;
  }
  // A player's photo, shown from her school's roster page; her initials if there is none.
  function face(p, cls) {
    var initials = p.name.split(/\s+/).map(function (w) { return w.charAt(0); }).join("").slice(0, 2).toUpperCase();
    var box = el("span", { "class": "face " + (cls || ""), "aria-hidden": "true" }, [el("span", { text: initials })]);
    if (p.photo) {
      var img = el("img", { src: p.photo, alt: "", loading: "lazy", decoding: "async", referrerpolicy: "no-referrer" });
      img.addEventListener("load", function () { box.classList.add("has"); });
      img.addEventListener("error", function () { if (img.parentNode) img.parentNode.removeChild(img); });
      box.appendChild(img);
    }
    return box;
  }
  function rankTag(rank) {
    return el("span", { "class": "rk" + (rank ? "" : " none"), text: rank ? String(rank) : "", "aria-label": rank ? "ranked " + rank : null });
  }

  // ---- the rankings page ----
  // The coaches poll beside the site's own GOAT ranking, which gives head-to-head results more say.
  var rankSort = "avca";
  function drawRanks() {
    var ol = $("ranks"), bar = $("rank-sort"), G = data.goat || {};
    ol.innerHTML = ""; bar.innerHTML = "";
    [["avca", "Order by AVCA poll"], ["goat", "Order by GOAT ranking"]].forEach(function (o) {
      bar.appendChild(el("button", { type: "button", "aria-pressed": String(rankSort === o[0]), text: o[1], onclick: function () { rankSort = o[0]; drawRanks(); } }));
    });
    var teams = data.poll.teams.slice();
    if (rankSort === "goat") teams.sort(function (a, b) { return (a.goat || 999) - (b.goat || 999); });
    teams.forEach(function (t) {
      var move = t.prev == null ? ["new", "up", "not ranked last week"] : t.prev > t.rank ? ["▲" + (t.prev - t.rank), "up", "up " + (t.prev - t.rank) + " from last week"]
        : t.prev < t.rank ? ["▼" + (t.rank - t.prev), "", "down " + (t.rank - t.prev) + " from last week"] : ["", "", ""];
      var name = t.id ? el("a", { "class": "nm", href: "#/", text: t.name, title: "Show " + t.name + "'s matches",
        onclick: function () { state.team = t.id; } }) : el("span", { "class": "nm", text: t.name });
      var diff = t.goat == null ? 0 : t.rank - t.goat;      // positive: the GOAT ranking has her higher than the poll
      ol.appendChild(el("li", {}, [rankTag(t.rank), el("span", { "class": "who" }, [logo(t.id), name]), el("span", { "class": "rec", text: t.record || "" }),
        el("span", { "class": "mv " + move[1], text: move[0], "aria-label": move[2] || null }),
        el("span", { "class": "goat" + (diff >= 3 ? " hi" : diff <= -3 ? " lo" : ""), text: t.goat == null ? "–" : String(t.goat),
          "aria-label": t.goat == null ? "no GOAT ranking" : "GOAT ranking " + t.goat,
          title: t.goat == null ? null : diff === 0 ? "Same place as the poll" : Math.abs(diff) + (Math.abs(diff) === 1 ? " place " : " places ") + (diff > 0 ? "higher" : "lower") + " than the poll" })]));
    });
    if (G.top) {
      $("goat-note").textContent = "GOAT is this site's own ranking of every Division I team. It starts from the team ratings behind the odds, then is rearranged to agree with as many head-to-head results as it can: a team climbs over one it has beaten when the two are close, but not when the ratings say the gap is wide. " +
        "Among these 25 teams the poll ranks a team below one it has beaten " + G.poll_wrong + " times; the GOAT ranking does " + G.goat_wrong + " times. A GOAT number is shaded when it is three or more places from the poll.";
      var out = G.top.filter(function (x) { return x.avca == null; });
      $("goat-out").textContent = out.length ? "In the GOAT top 25 but not in the poll: " + out.map(function (x) { return x.name + " (" + x.rank + ")"; }).join(", ") + "." : "";
    }
  }

  // ---- one match ----
  // [away, home] chances as whole percentages that add up to 100; never shown as 0 or 100
  function pct(home) { var n = Math.min(99, Math.max(1, Math.round(home * 100))); return [(100 - n) + "%", n + "%"]; }
  function oddsNote() {
    var t = data.odds_tested;
    return " Percentages are each team's chance of winning, from this site's own ratings of results, opponents and home court; they are not betting lines." +
      (t ? " Tested on " + t.matches.toLocaleString("en-US") + " past matches, the favorite won " + Math.round(t.favorite_won * 100) + "% of the time." : "");
  }
  function row(g) {
    // g.live is the score read from ESPN while the match is on (see "live scores" below)
    var L = g.live, fin = L ? L.state === "post" : g.state === "final", live = L ? L.state === "in" : g.state === "live";
    var as = L ? L.away : g.away.sets, hs = L ? L.home : g.home.sets, scored = (fin || live) && as != null && hs != null;
    var awayWon = fin && scored && as > hs, homeWon = fin && scored && hs > as;
    var t = g.start ? new Date(g.start * 1000) : null;
    var note = !L && g.state === "other" ? (g.note ? g.note.charAt(0).toUpperCase() + g.note.slice(1) : "Not played") : "";
    var when = fin ? "Final" : live ? (L && L.detail) || "In progress" : note ? note : t && !isNaN(t) ? t.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }) : "Time not set";
    function team(side, s, lost) {
      var kids = [logo(s.id), el("span", { "class": "name", text: s.name }), rankTag(s.rank)];
      if (side === "home") kids.reverse();
      return el("span", { "class": "team " + side + (lost ? " lost" : "") }, kids);
    }
    var pts = live && L && L.pts ? L.pts : null;      // points in the set being played: [away, home]
    function sets(cls, n, lost, p) {
      return el("span", { "class": cls + " " + (lost ? "l" : "w") }, [String(n), p != null ? el("small", { "class": "pt", text: String(p) }) : null]);
    }
    var mid = scored
      ? el("span", { "class": "mid", "aria-label": g.away.name + " " + as + ", " + g.home.name + " " + hs + " in sets" + (pts ? "; this set " + pts[0] + " to " + pts[1] : "") }, [
          sets("sa", as, homeWon, pts && pts[0]), el("span", { "class": "dash", text: "–" }), sets("sh", hs, awayWon, pts && pts[1]),
          pts ? el("span", { "class": "pts", text: pts[0] + "–" + pts[1] }) : null])
      : g.p != null && !fin
        // not started: each team's chance of winning, the favorite in bold
        ? el("span", { "class": "mid odds", "aria-label": g.away.name + " " + pct(g.p)[0] + ", " + g.home.name + " " + pct(g.p)[1] + " chance of winning" }, [
            el("span", { "class": "sa " + (g.p > 0.5 ? "l" : "w"), text: pct(g.p)[0] }), el("span", { "class": "dash", text: "at" }),
            el("span", { "class": "sh " + (g.p < 0.5 ? "l" : "w"), text: pct(g.p)[1] })])
        : el("span", { "class": "mid at", text: "at" });
    var more = [];
    if (g.round) more.push(g.round + " ");
    if (!fin && g.watch) {
      more.push(g.watch.length ? el("span", { "class": "watch" }, [el("span", { "class": "sr", text: "Watch on " }), g.watch.join(", ")])
        : el("span", { "class": "watch none", text: "No broadcast listed" }));
    }
    if (fin || live) more.push(el("a", { href: data.game_page + g.id, text: "Box score", rel: "noopener" }));
    return el("li", { "class": "game" + (g.away.rank && g.home.rank ? " both" : "") + (live ? " on" : ""), "data-id": g.id }, [
      el("span", { "class": "when" + (live ? " live" : ""), text: when }), team("away", g.away, homeWon), mid, team("home", g.home, awayWon),
      el("span", { "class": "more" }, more)]);
  }

  // ---- live scores ----
  // The site is rebuilt once a night, so while a match is on, the page reads
  // ESPN's public scoreboard itself and updates that match's row in place.
  var liveTimer = null;
  function ymd(g) { return g.date.replace(/-/g, ""); }
  function dueGames(now) {       // matches that could be under way: from 15 minutes before the start until 5 hours after
    return data.games.filter(function (g) {
      return g.espn && g.start && g.state !== "final" && !(g.live && g.live.state === "post") && now >= g.start - 900 && now <= g.start + 5 * 3600;
    });
  }
  function readLive(e) {
    var c = (e.competitions || [{}])[0], st = (e.status || {}).type || {}, out = { state: st.state, detail: st.shortDetail || st.detail || "" };
    (c.competitors || []).forEach(function (x) {
      var lines = x.linescores || [];
      out[x.homeAway] = x.score === "" || x.score == null ? null : +x.score;
      out[x.homeAway + "Pts"] = lines.length ? Math.round(lines[lines.length - 1].value) : null;
    });
    return out;
  }
  function pollLive() {
    clearTimeout(liveTimer);
    if (!data.live_feed) return;
    var now = Date.now() / 1000, due = dueGames(now), every = (data.live_seconds || 20) * 1000;
    if (document.hidden) return;                       // picks up again when the tab is shown
    if (!due.length) {                                 // nothing on: look again when the next match is close
      var next = data.games.filter(function (g) { return g.espn && g.start && g.state !== "final" && g.start - 900 > now; })
        .map(function (g) { return g.start - 900; }).sort(function (a, b) { return a - b; })[0];
      if (next) liveTimer = setTimeout(pollLive, Math.min(Math.max((next - now) * 1000, every), 6 * 3600 * 1000));
      showLiveNote(false);
      return;
    }
    var dates = {};
    due.forEach(function (g) { dates[ymd(g)] = 1; });
    Promise.all(Object.keys(dates).map(function (d) {
      return fetch(data.live_feed + d, { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : { events: [] }; }).catch(function () { return { events: [] }; });
    })).then(function (docs) {
      var byId = {};
      docs.forEach(function (doc) { (doc.events || []).forEach(function (e) { byId[e.id] = e; }); });
      var anyLive = false;
      due.forEach(function (g) {
        var e = byId[g.espn[0]];
        if (!e) return;
        var r = readLive(e), flip = g.espn[1];
        if (r.state !== "in" && r.state !== "post") return;                // not started yet
        var live = { state: r.state, detail: r.detail, away: flip ? r.home : r.away, home: flip ? r.away : r.home,
          pts: r.state === "in" && r.awayPts != null && r.homePts != null ? (flip ? [r.homePts, r.awayPts] : [r.awayPts, r.homePts]) : null };
        if (live.state === "in") anyLive = true;
        if (JSON.stringify(live) === JSON.stringify(g.live)) return;
        g.live = live;
        Array.prototype.forEach.call(document.querySelectorAll('.game[data-id="' + g.id + '"]'), function (li) { li.parentNode.replaceChild(row(g), li); });
      });
      showLiveNote(anyLive);
    }).then(function () { liveTimer = setTimeout(pollLive, every); });
  }
  function showLiveNote(on) {
    var n = $("live-note");
    n.hidden = !on;
    if (on) n.textContent = "Live scores from ESPN, refreshed every " + (data.live_seconds || 20) + " seconds. Big numbers are sets won; small numbers are points in the current set.";
  }
  document.addEventListener("visibilitychange", function () { if (data && !document.hidden) pollLive(); });

  function listInto(holder, games, newestFirst) {
    var days = {}, order = [];
    games.forEach(function (g) { if (!days[g.date]) { days[g.date] = []; order.push(g.date); } days[g.date].push(g); });
    if (newestFirst) order.reverse();
    order.forEach(function (d) {
      holder.appendChild(el("h3", { "class": "day" + (d === today ? " today" : ""), text: (d === today ? "Today, " : "") + long(d) }));
      holder.appendChild(el("ol", { "class": "games" }, days[d].map(row)));
    });
  }

  // ---- the page ----
  function draw() {
    var holder = $("list"), nav = $("nav"), head = $("h-list");
    holder.innerHTML = ""; nav.innerHTML = "";
    var weeks = {};
    data.games.forEach(function (g) { weeks[monday(g.date)] = 1; });
    var first = Object.keys(weeks).sort()[0], last = Object.keys(weeks).sort().pop();
    var pick = el("select", { id: "f-team", "aria-label": "Show one team", onchange: function () { state.team = pick.value || null; draw(); } },
      [el("option", { value: "", text: "All 25 teams" })].concat(data.poll.teams.filter(function (x) { return x.id; }).map(function (x) {
        return el("option", { value: x.id, text: x.rank + ". " + x.name, selected: x.id === state.team });
      })));
    nav.appendChild(pick);

    if (state.team) {
      var t = data.poll.teams.filter(function (x) { return x.id === state.team; })[0];
      var mine = data.games.filter(function (g) { return g.away.id === t.id || g.home.id === t.id; });
      head.textContent = "No. " + t.rank + " " + t.name + ", whole season";
      var next = mine.filter(function (g) { return g.state !== "final" && g.date >= today; }), done = mine.filter(function (g) { return g.state === "final" || g.date < today; });
      if (next.length) { holder.appendChild(el("p", { "class": "note", text: next.length + " still to play, " + done.length + " played." + oddsNote() })); listInto(holder, next); }
      if (done.length) { holder.appendChild(el("h3", { "class": "day", text: "Already played, newest first" })); listInto(holder, done, true); }
      if (!mine.length) holder.appendChild(el("p", { "class": "empty", text: "No matches are listed for " + t.name + " this season." }));
      return;
    }

    if (!state.week) {       // open on this week, or the nearest week that has matches
      var now = monday(today);
      state.week = !first ? now : now < first ? first : now > last ? last : now;
    }
    var w = state.week, end = addDays(w, 6), thisWeek = monday(today);
    var games = data.games.filter(function (g) { return g.date >= w && g.date <= end; });
    head.textContent = (w === thisWeek ? "This week, " : "Week of ") + short(w) + " to " + short(end);
    nav.appendChild(el("button", { type: "button", text: "Earlier week", disabled: !first || w <= first, onclick: function () { state.week = addDays(w, -7); draw(); } }));
    if (w !== thisWeek && first && thisWeek >= first && thisWeek <= last) nav.appendChild(el("button", { type: "button", text: "This week", onclick: function () { state.week = thisWeek; draw(); } }));
    nav.appendChild(el("button", { type: "button", text: "Later week", disabled: !last || w >= last, onclick: function () { state.week = addDays(w, 7); draw(); } }));
    if (!games.length) {
      holder.appendChild(el("p", { "class": "empty", text: "No ranked team has a match this week. Try an earlier or later week." }));
      return;
    }
    listInto(holder, games);
    var both = games.filter(function (g) { return g.away.rank && g.home.rank; }).length;
    holder.appendChild(el("p", { "class": "note", text: games.length + " matches this week" + (both ? ", " + both + " of them between two ranked teams (marked with a green edge)" : "") +
      ". The visiting team is on the left, and the channel or streaming service is on the right for matches in the next two weeks. Numbers are this week's rankings, also for earlier weeks. Choose a team to see its whole season." }));
    if (games.some(function (g) { return g.p != null && g.state !== "final"; })) holder.appendChild(el("p", { "class": "note", text: oddsNote().trim() }));
  }

  // ---- players ----
  var roster = null, pstate = { pos: "", team: "", q: "", all: false, sort: "rank", dir: 1 };
  var POS_ONE = { OH: "Outside or opposite hitter", MB: "Middle blocker", S: "Setter", L: "Libero", DS: "Defensive specialist" };
  var POS_MANY = { OH: "outside and opposite hitters", MB: "middle blockers", S: "setters", L: "liberos", DS: "defensive specialists" };
  var fmt = {
    d1: function (v) { return v.toFixed(1); }, d2: function (v) { return v.toFixed(2); },
    s1: function (v) { return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1); },
    s2: function (v) { return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(2); },
    hit: function (v) { return (v < 0 ? "−" : "") + Math.abs(v).toFixed(3).replace(/^0/, ""); },
    pct: function (v) { return v.toFixed(1) + "%"; }
  };
  // key, label, what it means, format
  var CARD = [
    ["Impact, in points added per set", "Against an average top-25 player at her position.", [
      ["impact_set", "All of it", "Everything below added together", fmt.s2],
      ["att", "Attack", "Kills minus errors, against the position's average on the same number of swings. She keeps three quarters; her setters get the rest", fmt.s2],
      ["srv", "Serve", "Aces minus service errors, against the average on the same number of serves", fmt.s2],
      ["rec", "Serve receive", "Reception errors avoided, against the position's average on the same number of receptions", fmt.s2],
      ["blk", "Block", "Blocks beyond the position's average per set", fmt.s2],
      ["dig", "Dig", "Digs beyond the position's average per set, at 0.3 of a point each", fmt.s2],
      ["set", "Setting", "A quarter of what her team's hitters added, shared among its setters by assists", fmt.s2]]],
    ["Attacking", "", [
      ["k_set", "Kills per set", "", fmt.d2], ["hit", "Hitting efficiency", "Kills minus errors, divided by swings", fmt.hit],
      ["kill_pct", "Kill rate", "Share of her swings that were kills", fmt.pct],
      ["err_pct", "Error rate", "Share of her swings that were errors. Fewer is better, so a long bar means few errors", fmt.pct],
      ["load", "Attack load", "Her share of the team's swings in the matches she played", fmt.pct],
      ["pts_set", "Points per set", "Kills, aces and blocks (half for each block assist) per set", fmt.d2]]],
    ["Serving", "", [
      ["ace_set", "Aces per set", "", fmt.d2], ["ace_pct", "Ace rate", "Aces per 100 serves", fmt.pct],
      ["se_pct", "Service error rate", "Errors per 100 serves. Fewer is better, so a long bar means few errors", fmt.pct]]],
    ["Passing, defense and setting", "", [
      ["re_pct", "Reception error rate", "Errors per 100 serve receptions. Fewer is better, so a long bar means few errors", fmt.pct],
      ["d_set", "Digs per set", "", fmt.d2], ["blk_set", "Blocks per set", "Solo blocks plus half of each block assist", fmt.d2],
      ["ast_set", "Assists per set", "", fmt.d2]]]
  ];
  function val(p, key) { return p.v[roster.metrics.indexOf(key)]; }
  function pctOf(p, key) { return p.pct[roster.metrics.indexOf(key)]; }
  function ordinal(n) { var s = ["th", "st", "nd", "rd"], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); }
  function loadRoster() {
    if (roster) return Promise.resolve(roster);
    return fetch("players.json", { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (d) { roster = d; return d; });
  }

  var PCOLS = [   // key, heading, meaning, getter, format, sorts high to low first
    ["rank", "#", "Rank by Impact among regulars", function (p) { return p.rank; }, function (v) { return String(v); }, 0],
    ["name", "Player", "", function (p) { return p.name; }, null, 0],
    ["team", "Team", "", function (p) { return p.team_rank; }, null, 0],
    ["pos", "Pos", "OH outside or opposite hitter, MB middle blocker, S setter, L libero, DS defensive specialist", function (p) { return p.pos; }, function (v) { return v; }, 0],
    ["sp", "Sets", "Sets played", function (p) { return p.sp; }, function (v) { return String(v); }, 1],
    ["impact", "Impact", "Points added this season over an average top-25 player at her position", function (p) { return p.impact; }, fmt.s1, 1],
    ["impact_set", "Per set", "Impact per set played", function (p) { return val(p, "impact_set"); }, fmt.s2, 1],
    ["k_set", "K/S", "Kills per set", function (p) { return val(p, "k_set"); }, fmt.d2, 1],
    ["hit", "Hit%", "Hitting efficiency: kills minus errors, divided by swings", function (p) { return p.tot.ta >= 10 ? val(p, "hit") : null; }, fmt.hit, 1],
    ["ast_set", "A/S", "Assists per set", function (p) { return val(p, "ast_set"); }, fmt.d2, 1],
    ["ace_set", "SA/S", "Aces per set", function (p) { return val(p, "ace_set"); }, fmt.d2, 1],
    ["d_set", "D/S", "Digs per set", function (p) { return val(p, "d_set"); }, fmt.d2, 1],
    ["blk_set", "B/S", "Blocks per set", function (p) { return val(p, "blk_set"); }, fmt.d2, 1]
  ];
  function drawPlayers() {
    var bar = $("p-filters"), holder = $("p-list");
    bar.innerHTML = ""; holder.innerHTML = "";
    holder.appendChild(el("p", { "class": "empty", text: "Loading the players…" }));
    loadRoster().then(function () {
      function pick(label, value, options, set) {
        var s = el("select", { "aria-label": label, onchange: function () { set(s.value); table(); } },
          options.map(function (o) { return el("option", { value: o[0], text: o[1], selected: o[0] === value }); }));
        return s;
      }
      bar.appendChild(pick("Position", pstate.pos, [["", "All positions"]].concat(Object.keys(POS_ONE).map(function (k) { return [k, POS_ONE[k] + "s"]; })), function (v) { pstate.pos = v; }));
      bar.appendChild(pick("Team", pstate.team, [["", "All 25 teams"]].concat(roster.teams.map(function (t) { return [t.id, t.rank + ". " + t.name]; })), function (v) { pstate.team = v; }));
      var q = el("input", { type: "search", placeholder: "Find a player", "aria-label": "Find a player", value: pstate.q, oninput: function () { pstate.q = q.value; table(); } });
      bar.appendChild(q);
      var chk = el("input", { type: "checkbox", id: "p-all", checked: pstate.all, onchange: function () { pstate.all = chk.checked; table(); } });
      bar.appendChild(el("label", { "class": "check", "for": "p-all" }, [chk, " Include part-time players"]));

      function table() {
        holder.innerHTML = "";
        var needle = pstate.q.trim().toLowerCase(), col = PCOLS.filter(function (c) { return c[0] === pstate.sort; })[0];
        var rows = roster.players.filter(function (p) {
          return (pstate.all || p.regular) && (!pstate.pos || p.pos === pstate.pos) && (!pstate.team || p.team_id === pstate.team) &&
            (!needle || p.name.toLowerCase().indexOf(needle) >= 0);
        }).sort(function (a, b) {
          var x = col[3](a), y = col[3](b);
          if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
          return typeof x === "string" ? pstate.dir * x.localeCompare(y) : pstate.dir * (x - y);
        });
        if (!rows.length) { holder.appendChild(el("p", { "class": "empty", text: "No player matches. Clear the search or choose all positions." })); return; }
        var head = el("tr", {}, PCOLS.map(function (c) {
          var on = pstate.sort === c[0];
          return el("th", { scope: "col", "class": c[0] === "name" || c[0] === "team" ? "l" : "", "aria-sort": on ? (pstate.dir > 0 ? "ascending" : "descending") : null }, [
            el("button", { type: "button", title: c[2] || null, text: c[1] + (on ? (pstate.dir > 0 ? " ▲" : " ▼") : ""),
              onclick: function () { if (on) pstate.dir = -pstate.dir; else { pstate.sort = c[0]; pstate.dir = c[5] ? -1 : 1; } table(); } })]);
        }));
        var body = el("tbody", {}, rows.map(function (p) {
          return el("tr", {}, PCOLS.map(function (c) {
            if (c[0] === "name") return el("td", { "class": "l nm" }, [el("a", { href: "#/player/" + encodeURIComponent(p.id) }, [face(p), el("span", { text: p.name })])]);
            if (c[0] === "team") return el("td", { "class": "l tm" }, [logo(p.team_id), el("span", { text: p.team })]);
            var v = c[3](p);
            return el("td", { "class": (c[0] === "impact" ? "strong " : "") + (pstate.sort === c[0] ? "sorted" : ""), text: v == null ? (c[0] === "rank" ? "–" : "") : c[4](v) });
          }));
        }));
        holder.appendChild(el("div", { "class": "tablewrap", tabindex: "0", role: "region", "aria-label": "Players table, scrolls sideways" }, [
          el("table", { "class": "ptable" }, [el("thead", {}, [head]), body])]));
        holder.appendChild(el("p", { "class": "note", text: rows.length + " players" + (roster.through ? ", through matches of " + short(roster.through) : "") +
          ". A regular has played at least " + Math.round(100 * roster.weights.regular_share) + "% of her team's sets; only regulars are ranked. Choose a name for her card, or a column heading to sort." }));
        holder.appendChild(el("p", { "class": "note", text: "Impact compares each player only with players on this week's top 25 teams, from official box scores. It cannot see pass quality or who was on the court, and it does not adjust for the opponent. A transfer counts as a new player at her new school." }));
      }
      table();
    }).catch(function () {
      holder.innerHTML = "";
      holder.appendChild(el("p", { "class": "empty", text: "The players could not be loaded. Reload the page to try again." }));
    });
  }

  function drawCard(id) {
    var holder = $("card");
    holder.innerHTML = "";
    loadRoster().then(function () {
      var p = roster.players.filter(function (x) { return x.id === id; })[0];
      if (!p) { holder.appendChild(el("p", { "class": "empty", text: "There is no card for that player. Her team may have dropped out of the top 25." })); return; }
      document.title = p.name + " | " + data.site;
      var many = POS_MANY[p.pos], nPos = roster.pos_regulars[p.pos] || 0;
      var art = el("article", { "class": "pcard" });
      art.appendChild(el("header", { "class": "pc-head" }, [
        face(p, "big"),
        el("div", { "class": "pc-id" }, [
          el("h1", { text: p.name }),
          el("p", { "class": "pc-team" }, [logo(p.team_id), el("span", { text: p.team + " (ranked " + p.team_rank + ")" })]),
          el("p", { text: (p.num != null ? "No. " + p.num + ", " : "") + POS_ONE[p.pos].toLowerCase() }),
          el("p", { "class": "pc-sub", text: p.sp + " sets in " + p.mp + " matches, " + p.starts + " starts" })]),
        el("div", { "class": "pc-rank" }, p.regular ? [
          el("b", { text: ordinal(p.rank) }), el("span", { text: "of " + roster.regulars + " regulars" }),
          el("span", { text: ordinal(p.pos_rank) + " of " + nPos + " " + many })] : [
          el("b", { text: "–" }), el("span", { text: "Not ranked: too few sets" })])
      ]));
      art.appendChild(el("p", { "class": "pc-impact" }, [el("b", { text: fmt.s1(p.impact) }), " points added this season, ", el("b", { text: fmt.s2(val(p, "impact_set")) }), " per set."]));
      CARD.forEach(function (sec) {
        var rows = sec[2].filter(function (m) { return pctOf(p, m[0]) != null; });
        if (!rows.length) return;
        var box = el("section", { "class": "pc-sec" }, [el("h2", { text: sec[0] })]);
        if (sec[1]) box.appendChild(el("p", { "class": "pc-secnote", text: sec[1] }));
        rows.forEach(function (m) {
          var pc = pctOf(p, m[0]), v = val(p, m[0]);
          box.appendChild(el("div", { "class": "prow", title: m[2] || null }, [
            el("span", { "class": "plabel", text: m[1] }),
            el("span", { "class": "ptrack", role: "img", "aria-label": m[1] + ": " + ordinal(pc) + " percentile" }, [
              el("i", { "class": pc >= 67 ? "hi" : pc >= 34 ? "mid" : "lo", style: "width:" + Math.max(pc, 2) + "%" })]),
            el("b", { "class": "ppct", text: String(pc) }),
            el("span", { "class": "pval", text: v == null ? "" : m[3](v) })]));
        });
        art.appendChild(box);
      });
      if (!p.regular) art.appendChild(el("p", { "class": "note", text: "Percentiles are given only to regulars: players with at least " + Math.round(100 * roster.weights.regular_share) + "% of their team's sets." }));
      var t = p.tot, totals = [["Kills", t.k], ["Errors", t.e], ["Swings", t.ta], ["Assists", t.ast], ["Aces", t.sa], ["Service errors", t.se], ["Serves", t.sv],
        ["Digs", t.d], ["Receptions", t.ra], ["Reception errors", t.re], ["Solo blocks", t.bs], ["Block assists", t.ba], ["Points", t.pts]];
      art.appendChild(el("section", { "class": "pc-sec" }, [el("h2", { text: "Season totals" }),
        el("dl", { "class": "totals" }, totals.reduce(function (a, x) { return a.concat([el("div", {}, [el("dt", { text: x[0] }), el("dd", { text: String(x[1]) })])]); }, []))]));
      art.appendChild(el("p", { "class": "note", text: "The number beside each bar is her percentile among " + many + " who play regularly for a top-25 team and do that job: 90 means better than 90% of them. The tick marks the middle." +
        (roster.through ? " Through matches of " + short(roster.through) + "." : "") }));
      var defs = [];
      CARD.forEach(function (sec) { sec[2].forEach(function (m) { if (m[2] && pctOf(p, m[0]) != null) defs.push(el("div", {}, [el("dt", { text: m[1] }), el("dd", { text: m[2] + "." })])); }); });
      art.appendChild(el("details", { "class": "defs" }, [el("summary", { text: "What each line measures" }), el("dl", {}, defs)]));
      holder.appendChild(art);
    }).catch(function () {
      holder.appendChild(el("p", { "class": "empty", text: "The card could not be loaded. Reload the page to try again." }));
    });
  }

  function route() {
    var h = location.hash, card = /^#\/?player\/(.+)$/.exec(h);
    var page = card ? "card" : /^#\/?players/.test(h) ? "players" : /^#\/?rankings/.test(h) ? "rankings" : "matches";
    ["matches", "rankings", "players", "card"].forEach(function (p) { $("page-" + p).hidden = p !== page; });
    Array.prototype.forEach.call(document.querySelectorAll(".pages a"), function (a) {
      if (a.dataset.page === (page === "card" ? "players" : page)) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    document.title = ({ rankings: "Top 25 rankings", players: "Top 25 players", card: "Player card" }[page] || "Top 25 matches") + " | " + data.site;
    if (page === "rankings") drawRanks(); else if (page === "players") drawPlayers(); else if (page === "card") drawCard(decodeURIComponent(card[1])); else draw();
    window.scrollTo(0, 0);
  }

  fetch("data.json", { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (d) {
    data = d;
    $("brand").textContent = d.site;
    $("lede").textContent = "Every match played by a team in the " + d.poll.name + ", week by week.";
    $("rank-lede").textContent = "The " + d.poll.name + ", through matches of " + day(d.poll.through).toLocaleDateString(undefined, { month: "long", day: "numeric" }) + ", beside this site's GOAT ranking.";
    $("rank-note").textContent = "Record and change are from the poll, which is checked for a new one every Monday. The GOAT ranking is redone every night. Choose a team to see its matches.";
    var u = new Date(d.updated);
    $("foot-updated").textContent = "Scores and schedule updated " + (isNaN(u) ? d.updated : u.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })) +
      ". Rankings: " + d.poll.name + " through " + day(d.poll.through).toLocaleDateString(undefined, { dateStyle: "long" }) + ".";
    window.addEventListener("hashchange", route);
    route();
    pollLive();
  }).catch(function () {
    $("h-list").textContent = "The matches could not be loaded";
    $("list").appendChild(el("p", { "class": "empty", text: "Reload the page to try again. If this keeps happening, the nightly update may not have run yet." }));
  });
})();

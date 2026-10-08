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

  // A team's logo, served by ncaa.com and shown in one colour. With `name`, the logo
  // stands in for the team's name, so it carries the name for screen readers and on hover.
  function logo(teamId, cls, name) {
    if (!data.logo || !teamId) return name ? el("span", { text: name }) : null;
    var img = el("img", { src: data.logo.replace("{team}", encodeURIComponent(teamId)), alt: name || "", title: name || null, loading: "lazy", decoding: "async" });
    var pic = el("span", { "class": "logo " + (cls || "") }, [img]);
    img.addEventListener("error", function () {       // no logo for this school: show the name instead, or leave the space
      if (name) { pic.className = ""; pic.textContent = name; } else pic.style.visibility = "hidden";
    });
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
  // A team's name as a link to its page.
  function teamA(id, name, cls) {
    return id ? el("a", { "class": "tlink " + (cls || ""), href: "#/team/" + encodeURIComponent(id), text: name })
      : el("span", { "class": cls || "", text: name });
  }
  // The site's wording, from words.txt (see the top of that file). {name} is filled from `vars`.
  function W(key, vars) {
    var s = ((data && data.words) || {})[key];
    if (s == null) return "";
    return s.replace(/\{(\w+)\}/g, function (m, k) { return vars && vars[k] != null ? String(vars[k]) : m; });
  }
  // ---- Top 25 or all of Division I: one switch, remembered, used by every page that has it ----
  var scope = "top25";
  try { if (localStorage.getItem("scope") === "d1") scope = "d1"; } catch (e) {}
  function isD1() { return scope === "d1"; }
  function rankOf(id) { for (var i = 0; i < data.poll.teams.length; i++) if (data.poll.teams[i].id === id) return data.poll.teams[i]; return null; }
  function setScope(s) { scope = s; try { localStorage.setItem("scope", s); } catch (e) {} }
  function scopeSwitch(redraw, lockTop) {
    return el("div", { "class": "scope", role: "group", "aria-label": "Which teams" }, [["top25", W("scope.top25")], ["d1", W("scope.d1")]].map(function (o) {
      var on = lockTop ? o[0] === "d1" : scope === o[0];      // a team outside the top 25 is always shown against all of D1
      return el("button", { type: "button", "aria-pressed": String(on), disabled: lockTop && o[0] === "top25",
        text: o[1], onclick: function () { if (!on) { setScope(o[0]); redraw(); } } });
    }));
  }
  function setHead(page, key) {      // a page's title and intro for the current switch
    var sec = $("page-" + page), h = sec && sec.querySelector("h1"), l = sec && sec.querySelector(".lede");
    if (h) h.textContent = W(key + ".title" + (isD1() ? "_d1" : ""));
    if (l && W(key + ".lede" + (isD1() ? "_d1" : ""))) l.textContent = W(key + ".lede" + (isD1() ? "_d1" : ""), { poll: data.poll.name });
  }
  // A team's number: its AVCA rank, or for a team outside the poll its place
  // from 26 on in the GOAT ranking (data.nr), so no two teams share a number.
  function shownRank(id, rank) { return rank || (id && data.nr && data.nr[id]) || null; }
  function rankTag(rank, id) {
    var n = shownRank(id, rank);
    return el("span", { "class": "rk" + (n ? "" : " nr"), text: n ? String(n) : "NR",
      "aria-label": rank ? "ranked " + rank : n ? "unranked, " + n + " by the GOAT ranking" : "unranked", title: !rank && n ? "Not in the AVCA poll; " + n + " by the GOAT ranking" : null });
  }

  // ---- the rankings page ----
  // The coaches poll beside the site's own GOAT ranking, which gives head-to-head results more say.
  var rankView = "avca", goatAll = false;      // the poll is shown; the GOAT ranking only when asked for
  // A team's results against the other ranked teams: "Beat 9 Texas, 12 Texas A&M. Lost to 2 Pittsburgh."
  // Two boxes under the team, side by side: "Beat" on the left, "Lost to" on the right.
  function versus(t) {
    function box(label, rows, cls) {
      var opps = rows.map(function (r) {
        return el("a", { "class": "opp", href: "#/team/" + encodeURIComponent(r[3]), title: r[1] }, [el("span", { "class": "n", text: String(r[0]) }), logo(r[3], "sm", r[1]), r[2] > 1 ? el("span", { "class": "x", text: "×" + r[2] }) : null]);
      });
      return el("span", { "class": "vsbox " + cls }, [el("b", { text: label }),
        el("span", { "class": "opps" }, opps.length ? opps : [el("span", { "class": "nil", text: W("rankings.none_yet") })])]);
    }
    return el("span", { "class": "vs" }, [box(W("rankings.beat"), t.beat || [], "beat"), box(W("rankings.lost_to"), t.lost || [], "lostto")]);
  }
  function drawRanks() {
    var ol = $("ranks"), bar = $("rank-sort"), head = $("ranks-head"), G = data.goat || {}, goatView = rankView === "goat" && G.top;
    ol.innerHTML = ""; bar.innerHTML = ""; head.innerHTML = "";
    [["avca", W("rankings.button_poll")], ["goat", W("rankings.button_goat")]].forEach(function (o) {
      bar.appendChild(el("button", { type: "button", "aria-pressed": String(rankView === o[0]), text: o[1], onclick: function () { rankView = o[0]; drawRanks(); } }));
    });
    (goatView ? ["GOAT", "Team", "Record", "AVCA"] : ["AVCA", "Team", "Record", "Change"]).forEach(function (h) { head.appendChild(el("span", { text: h })); });
    // on a wide screen the Beat and Lost to boxes sit in the row, under these two headings
    head.appendChild(el("span", { "class": "wide beat", text: W("rankings.beat") }));
    head.appendChild(el("span", { "class": "wide lostto", text: W("rankings.lost_to") }));
    function teamLink(id, name) { return teamA(id, name, "nm"); }
    var polled = {};
    data.poll.teams.forEach(function (t) { if (t.id) polled[t.id] = 1; });
    if (goatView) {
      (goatAll ? G.top : G.top.slice(0, 25)).forEach(function (t) {
        ol.appendChild(el("li", {}, [rankTag(t.rank), el("span", { "class": "who" }, [logo(t.id), teamLink(t.id, t.name)]),
          el("span", { "class": "rec", text: t.record || "" }),
          el("span", { "class": "mv", text: t.avca == null ? "–" : String(t.avca), "aria-label": t.avca == null ? "not in the AVCA poll" : "AVCA poll " + t.avca }),
          versus(t)]));
      });
    } else {
      data.poll.teams.forEach(function (t) {
        var move = t.prev == null ? ["new", "up", "not ranked last week"] : t.prev > t.rank ? ["▲" + (t.prev - t.rank), "up", "up " + (t.prev - t.rank) + " from last week"]
          : t.prev < t.rank ? ["▼" + (t.rank - t.prev), "", "down " + (t.rank - t.prev) + " from last week"] : ["", "", ""];
        ol.appendChild(el("li", {}, [rankTag(t.rank), el("span", { "class": "who" }, [logo(t.id), teamLink(t.id, t.name)]), el("span", { "class": "rec", text: t.record || "" }),
          el("span", { "class": "mv " + move[1], text: move[0], "aria-label": move[2] || null }), versus(t)]));
      });
    }
    var through = day(data.poll.through).toLocaleDateString(undefined, { month: "long", day: "numeric" });
    $("rank-lede").textContent = goatView ? W("rankings.lede_goat") : W("rankings.lede", { poll: data.poll.name, date: through });
    $("rank-note").textContent = goatView ? W("rankings.note_goat") : W("rankings.note");
    $("goat-note").textContent = !goatView ? "" : "Every Division I team is ranked on four things, most important first: head to head, strength of schedule (the average rating of the teams played), its place in the AVCA poll, and its record. " +
      "A team is ranked above one it has beaten unless the other three say the gap is wide. Elsewhere on the site, teams outside the poll are numbered from 26 in this order. " +
      "Among the poll's 25 teams, the poll ranks a team below one it has beaten " + G.poll_wrong + " times; the GOAT ranking does " + G.goat_wrong + " times.";
    var out = $("goat-out");
    out.textContent = "";
    if (goatView && G.top.length > 25) out.appendChild(el("button", { type: "button", "class": "morebtn",
      text: goatAll ? W("rankings.show_top") : W("rankings.show_all", { n: G.top.length }), onclick: function () { goatAll = !goatAll; drawRanks(); } }));
  }

  // ---- one match ----
  // [away, home] chances as whole percentages that add up to 100; never shown as 0 or 100
  function pct(home) { var n = Math.min(99, Math.max(1, Math.round(home * 100))); return [(100 - n) + "%", n + "%"]; }
  function oddsNote() {
    var t = data.odds_tested;
    return " Percentages are each team's chance of winning, from this site's own ratings of results, opponents and home court; they are not betting lines." +
      (t ? " Tested on " + t.matches.toLocaleString("en-US") + " past matches, the favorite won " + Math.round(t.favorite_won * 100) + "% of the time." : "");
  }
  function liveTag() { return el("span", { "class": "livetag" }, [el("span", { "class": "dot", "aria-hidden": "true" }), W("matches.live")]); }
  function row(g) {
    // g.live is the score read from ESPN while the match is on (see "live scores" below)
    var L = g.live, fin = L ? L.state === "post" : g.state === "final", live = L ? L.state === "in" : g.state === "live";
    var as = L ? L.away : g.away.sets, hs = L ? L.home : g.home.sets, scored = (fin || live) && as != null && hs != null;
    var awayWon = fin && scored && as > hs, homeWon = fin && scored && hs > as;
    var t = g.start ? new Date(g.start * 1000) : null;
    var note = !L && g.state === "other" ? (g.note ? g.note.charAt(0).toUpperCase() + g.note.slice(1) : "Not played") : "";
    var when = fin ? "Final" : live ? (L && L.detail) || "In progress" : note ? note : t && !isNaN(t) ? t.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }) : "Time not set";
    function team(side, s, lost, won) {
      var kids = [logo(s.id), teamA(s.id, s.name, "name"), rankTag(s.rank, s.id)];
      if (side === "home") kids.reverse();
      return el("span", { "class": "team " + side + (lost ? " lost" : "") + (won ? " won" : "") }, kids);
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
        : el("span", { "class": "watch none", text: W("matches.no_broadcast") }));
    }
    if (fin || live) more.push(el("a", { href: "#/match/" + g.id, text: live ? W("matches.live_box_score") : W("matches.box_score") }));
    var unplayed = !fin && !live && !note;
    return el("li", { "class": "game" + (g.away.rank && g.home.rank ? " both" : "") + (live ? " on" : "") + (unplayed ? " ahead" : ""), "data-id": g.id }, [
      live ? el("span", { "class": "when live" }, [liveTag(), " " + (when === "In progress" ? "" : when)]) : el("span", { "class": "when", text: when }),
      team("away", g.away, homeWon, awayWon), mid, team("home", g.home, awayWon, homeWon),
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
    setHead("matches", "matches");
    var shown = isD1() ? data.games : data.games.filter(function (g) { return g.away.rank || g.home.rank; });
    var teamsHere = isD1() ? data.d1.map(function (x) { var r = rankOf(x[0]); return { id: x[0], name: x[1], rank: shownRank(x[0], r && r.rank) }; })
        .sort(function (a, b) { return (a.rank || 9999) - (b.rank || 9999) || a.name.localeCompare(b.name); })
      : data.poll.teams.filter(function (x) { return x.id; });
    if (state.team && !teamsHere.some(function (x) { return x.id === state.team; })) state.team = null;
    nav.appendChild(scopeSwitch(draw));
    // which side is which: over the columns on a wide screen, beside the two lines on a phone
    holder.appendChild(el("div", { "class": "hahead", "aria-hidden": "true" }, [el("span"), el("span", { "class": "ha away", text: W("matches.away") }),
      el("span"), el("span", { "class": "ha home", text: W("matches.home") }), el("span")]));
    var weeks = {};
    shown.forEach(function (g) { weeks[monday(g.date)] = 1; });
    var first = Object.keys(weeks).sort()[0], last = Object.keys(weeks).sort().pop();
    var pick = el("select", { id: "f-team", "aria-label": "Show one team", onchange: function () { state.team = pick.value || null; draw(); } },
      [el("option", { value: "", text: isD1() ? W("matches.all_teams_d1") : W("matches.all_teams") })].concat(teamsHere.map(function (x) {
        return el("option", { value: x.id, text: (x.rank ? x.rank + ". " : "") + x.name, selected: x.id === state.team });
      })));
    nav.appendChild(pick);

    if (state.team) {
      var t = teamsHere.filter(function (x) { return x.id === state.team; })[0];
      var mine = data.games.filter(function (g) { return g.away.id === t.id || g.home.id === t.id; });
      head.innerHTML = "";
      head.appendChild(logo(t.id));
      head.appendChild(document.createTextNode(" " + (t.rank ? "No. " + t.rank + " " : "") + t.name + ", whole season"));
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
    var games = shown.filter(function (g) { return g.date >= w && g.date <= end; });
    head.textContent = (w === thisWeek ? "This week, " : "Week of ") + short(w) + " to " + short(end);
    nav.appendChild(el("button", { type: "button", text: W("matches.earlier"), disabled: !first || w <= first, onclick: function () { state.week = addDays(w, -7); draw(); } }));
    if (w !== thisWeek && first && thisWeek >= first && thisWeek <= last) nav.appendChild(el("button", { type: "button", text: W("matches.this_week"), onclick: function () { state.week = thisWeek; draw(); } }));
    nav.appendChild(el("button", { type: "button", text: W("matches.later"), disabled: !last || w >= last, onclick: function () { state.week = addDays(w, 7); draw(); } }));
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
  var roster = null, pstate = { pos: "", team: "", q: "", all: false, sort: "impact_set", dir: -1 };
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
  var rosters = {};
  function loadRoster(which) {     // players rated against the top 25, or against all of Division I
    which = which || scope;
    if (rosters[which]) { roster = rosters[which]; return Promise.resolve(roster); }
    return fetch(which === "d1" ? "players_d1.json" : "players.json", { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) { rosters[which] = d; roster = d; return d; });
  }

  var PCOLS = [   // key, heading, meaning, getter, format, sorts high to low first
    ["rank", "#", "Rank by Impact per set among regulars", function (p) { return p.rank; }, function (v) { return String(v); }, 0],
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
    setHead("players", "players");
    holder.appendChild(el("p", { "class": "empty", text: "Loading the players…" }));
    loadRoster().then(function () {
      bar.appendChild(scopeSwitch(function () { pstate.team = ""; pstate.limit = 200; drawPlayers(); }));
      function pick(label, value, options, set) {
        var s = el("select", { "aria-label": label, onchange: function () { set(s.value); pstate.limit = 200; table(); } },
          options.map(function (o) { return el("option", { value: o[0], text: o[1], selected: o[0] === value }); }));
        return s;
      }
      bar.appendChild(pick("Position", pstate.pos, [["", "All positions"]].concat(Object.keys(POS_ONE).map(function (k) { return [k, POS_ONE[k] + "s"]; })), function (v) { pstate.pos = v; }));
      bar.appendChild(pick("Team", pstate.team, [["", W("matches.all_teams")]].concat(roster.teams.slice().sort(function (a, b) { return (shownRank(a.id, a.rank) || 9999) - (shownRank(b.id, b.rank) || 9999) || a.name.localeCompare(b.name); })
        .map(function (t) { var n = shownRank(t.id, t.rank); return [t.id, (n ? n + ". " : "") + t.name]; })), function (v) { pstate.team = v; }));
      var q = el("input", { type: "search", placeholder: "Find a player", "aria-label": "Find a player", value: pstate.q, oninput: function () { pstate.q = q.value; pstate.limit = 200; table(); } });
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
        var total = rows.length, limit = pstate.limit || 200;
        rows = rows.slice(0, limit);
        var body = el("tbody", {}, rows.map(function (p) {
          return el("tr", {}, PCOLS.map(function (c) {
            if (c[0] === "name") return el("td", { "class": "l nm" }, [el("a", { href: "#/player/" + encodeURIComponent(p.id) }, [el("span", { text: p.name })])]);
            if (c[0] === "team") return el("td", { "class": "l" }, [el("span", { "class": "tcell tm" }, [logo(p.team_id), teamA(p.team_id, p.team)])]);
            var v = c[3](p);
            return el("td", { "class": (c[0] === "impact_set" ? "strong " : "") + (pstate.sort === c[0] ? "sorted" : ""), text: v == null ? (c[0] === "rank" ? "–" : "") : c[4](v) });
          }));
        }));
        holder.appendChild(el("div", { "class": "tablewrap", tabindex: "0", role: "region", "aria-label": "Players table, scrolls sideways" }, [
          el("table", { "class": "ptable pltable" }, [el("thead", {}, [head]), body])]));
        if (total > rows.length) holder.appendChild(el("p", { "class": "more" }, [el("button", { type: "button", "class": "morebtn", text: "Show " + Math.min(400, total - rows.length) + " more of " + total,
          onclick: function () { pstate.limit = limit + 400; table(); } })]));
        holder.appendChild(el("p", { "class": "note", text: total + " players" + (roster.through ? ", through matches of " + short(roster.through) : "") +
          ". A regular has played at least " + Math.round(100 * roster.weights.regular_share) + "% of her team's sets; only regulars are ranked. Choose a name for her card, or a column heading to sort." }));
        holder.appendChild(el("p", { "class": "note", text: W(isD1() ? "players.note_d1" : "players.note") }));
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
    var team = id.split("~")[0], ranked = !!rankOf(team);
    loadRoster(ranked ? scope : "d1").then(function () {
      var p = roster.players.filter(function (x) { return x.id === id; })[0];
      if (!p) { holder.appendChild(el("p", { "class": "empty", text: "There is no card for that player. She may not have played a set yet this season." })); return; }
      holder.appendChild(el("div", { "class": "nav filters" }, [scopeSwitch(function () { drawCard(id); }, !ranked)]));
      if (!ranked) holder.appendChild(el("p", { "class": "note", text: "Her team is not in the top 25, so she is measured against all of Division I." }));
      document.title = p.name + " | " + data.site;
      var many = POS_MANY[p.pos], nPos = roster.pos_regulars[p.pos] || 0;
      var art = el("article", { "class": "pcard" });
      art.appendChild(el("header", { "class": "pc-head" }, [
        face(p, "big"),
        el("div", { "class": "pc-id" }, [
          el("h1", { text: p.name }),
          el("p", { "class": "pc-team" }, [logo(p.team_id), teamA(p.team_id, p.team), p.team_rank ? el("span", { text: " (ranked " + p.team_rank + ")" }) : null]),
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

  // ---- the teams page: each ranked team's stats, from box scores ----
  var teamStats = null, tstate = { sort: "rank", dir: 1 };
  var teamSets = {};
  function loadTeams(which) {      // the ranked 25, or all of Division I
    which = which || scope;
    if (teamSets[which]) return Promise.resolve(teamSets[which]);
    return fetch(which === "d1" ? "teams_d1.json" : "teams.json", { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) { teamSets[which] = d; return d; });
  }
  function hitFmt(v) { return (v < 0 ? "-" : "") + Math.abs(v).toFixed(3).replace(/^0/, ""); }
  var TCOLS = [   // key, heading, meaning, getter, format, sorts high to low first
    ["rank", "Rank", "AVCA poll rank; teams outside the poll are numbered from 26 in GOAT ranking order", function (t) { return shownRank(t.id, t.rank); }, String, 0],
    ["name", "Team", "", function (t) { return t.name; }, null, 0],
    ["rec", "W-L", "Matches won and lost", function (t) { return t.w + t.l ? t.w / (t.w + t.l) : null; }, null, 1],
    ["set_pct", "Sets", "Sets won and lost", function (t) { return t.set_pct; }, null, 1],
    ["hit", "Hit%", "Hitting efficiency: kills minus errors, divided by swings", function (t) { return t.hit; }, hitFmt, 1],
    ["opp_hit", "Opp Hit%", "Opponents' hitting efficiency against this team. Lower is better", function (t) { return t.opp_hit; }, hitFmt, 0],
    ["k_set", "K/S", "Kills per set", function (t) { return t.k_set; }, fmt.d2, 1],
    ["opp_k_set", "Opp K/S", "Opponents' kills per set. Lower is better", function (t) { return t.opp_k_set; }, fmt.d2, 0],
    ["ast_set", "A/S", "Assists per set", function (t) { return t.ast_set; }, fmt.d2, 1],
    ["sa_set", "SA/S", "Aces per set", function (t) { return t.sa_set; }, fmt.d2, 1],
    ["se_set", "SE/S", "Service errors per set. Lower is better", function (t) { return t.se_set; }, fmt.d2, 0],
    ["blk_set", "B/S", "Blocks per set: solo blocks plus half of each block assist", function (t) { return t.blk_set; }, fmt.d2, 1],
    ["d_set", "D/S", "Digs per set", function (t) { return t.d_set; }, fmt.d2, 1],
    ["re_pct", "RE%", "Reception errors per 100 serves received. Lower is better", function (t) { return t.re_pct; }, function (v) { return v.toFixed(1); }, 0],
    ["power", "Rating", "Where this site's rating (the one behind the odds) places the team among all Division I teams", function (t) { return t.power; }, String, 0],
    ["sos_rank", "SOS", "Strength of schedule among the teams shown: 1 is the hardest, by the average rating of the teams played", function (t) { return t.sos_rank; }, String, 0]
  ];
  function drawTeams() {
    var holder = $("t-list");
    holder.innerHTML = "";
    setHead("teams", "teams");
    holder.appendChild(el("p", { "class": "empty", text: "Loading the team stats…" }));
    loadTeams().then(function (d) {
      function table() {
        holder.innerHTML = "";
        holder.appendChild(el("div", { "class": "nav filters" }, [scopeSwitch(drawTeams)]));
        var col = TCOLS.filter(function (c) { return c[0] === tstate.sort; })[0];
        var rows = d.teams.slice().sort(function (a, b) {
          var x = col[3](a), y = col[3](b);
          if (x == null && y == null) return (a.power || 999) - (b.power || 999); if (x == null) return 1; if (y == null) return -1;
          return (typeof x === "string" ? tstate.dir * x.localeCompare(y) : tstate.dir * (x - y)) || (a.power || 999) - (b.power || 999);
        });
        var head = el("tr", {}, TCOLS.map(function (c) {
          var on = tstate.sort === c[0];
          return el("th", { scope: "col", "class": c[0] === "name" ? "l" : "", "aria-sort": on ? (tstate.dir > 0 ? "ascending" : "descending") : null }, [
            el("button", { type: "button", title: c[2] || null, text: c[1] + (on ? (tstate.dir > 0 ? " ▲" : " ▼") : ""),
              onclick: function () { if (on) tstate.dir = -tstate.dir; else { tstate.sort = c[0]; tstate.dir = c[5] ? -1 : 1; } table(); } })]);
        }));
        var body = el("tbody", {}, rows.map(function (t) {
          return el("tr", {}, TCOLS.map(function (c) {
            var cls = tstate.sort === c[0] ? "sorted" : "";
            if (c[0] === "rank") return el("td", { "class": cls }, [rankTag(t.rank, t.id)]);
            if (c[0] === "name") return el("td", { "class": "l " + cls }, [el("span", { "class": "tcell" }, [logo(t.id), teamA(t.id, t.name)])]);
            if (c[0] === "rec") return el("td", { "class": cls, text: t.w + "-" + t.l });
            if (c[0] === "set_pct") return el("td", { "class": cls, text: t.sw + "-" + t.sl });
            var v = c[3](t);
            return el("td", { "class": cls, text: v == null ? "" : c[4](v) });
          }));
        }));
        holder.appendChild(el("div", { "class": "tablewrap", tabindex: "0", role: "region", "aria-label": "Team stats table, scrolls sideways" }, [
          el("table", { "class": "ptable ttable" }, [el("thead", {}, [head]), body])]));
        holder.appendChild(el("p", { "class": "note", text: (d.through ? "Through matches of " + short(d.through) + ". " : "") +
          W(isD1() ? "teams.note_d1" : "teams.note") }));
      }
      table();
    }).catch(function () {
      holder.innerHTML = "";
      holder.appendChild(el("p", { "class": "empty", text: "The team stats could not be loaded. Reload the page to try again." }));
    });
  }

  // ---- a match's own page: set scores (ESPN, live) and both teams' box scores (NCAA, via the site's job) ----
  var matchTimers = [];
  function stopMatch() { matchTimers.forEach(clearTimeout); matchTimers = []; }
  var ESPN_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/volleyball/womens-college-volleyball/summary?event=";
  var BCOLS = [   // heading, meaning, value from a row: [num, name, pos, starter, sets, k, e, ta, ast, sa, se, d, ra, re, bs, ba, bhe, id, photo]
    ["S", "Sets played", function (r) { return r[4]; }],
    ["K", "Kills", function (r) { return r[5]; }], ["E", "Attack errors", function (r) { return r[6]; }], ["TA", "Total attacks", function (r) { return r[7]; }],
    ["Hit%", "Hitting efficiency", function (r) { return r[7] ? hitFmt((r[5] - r[6]) / r[7]) : ""; }],
    ["A", "Assists", function (r) { return r[8]; }], ["SA", "Service aces", function (r) { return r[9]; }], ["SE", "Service errors", function (r) { return r[10]; }],
    ["D", "Digs", function (r) { return r[11]; }], ["RE", "Reception errors", function (r) { return r[13]; }],
    ["BS", "Solo blocks", function (r) { return r[14]; }], ["BA", "Block assists", function (r) { return r[15]; }],
    ["PTS", "Points: kills, aces, solo blocks and half of each block assist", function (r) { var p = r[5] + r[9] + r[14] + r[15] / 2; return p % 1 ? p.toFixed(1) : String(p); }]
  ];
  function boxTable(side, rows, name) {
    var tot = [null, "Team", "", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    rows.forEach(function (r) { for (var i = 5; i <= 16; i++) tot[i] += r[i] || 0; tot[4] = Math.max(tot[4], r[4] || 0); });
    var head = el("tr", {}, [el("th", { scope: "col", "class": "l" }, [el("span", { text: "#" })]), el("th", { scope: "col", "class": "l", text: name })]
      .concat(BCOLS.map(function (c) { return el("th", { scope: "col", title: c[1], text: c[0] }); })));
    function pts(r) { return r[5] + r[9] + r[14] + r[15] / 2; }
    rows = rows.slice().sort(function (a, b) { return (b[3] - a[3]) || (pts(b) - pts(a)) || (b[11] - a[11]); });   // starters first, then by points
    var body = el("tbody", {}, rows.map(function (r) {
      var who = r[17] ? el("a", { href: "#/player/" + encodeURIComponent(r[17]) }, [face({ name: r[1], photo: r[18] }), el("span", { text: r[1] })])
        : el("span", { "class": "plain" }, [face({ name: r[1] }), el("span", { text: r[1] })]);
      return el("tr", { "class": r[3] ? "starter" : "" }, [el("td", { "class": "l", text: r[0] == null ? "" : String(r[0]) }), el("td", { "class": "l nm" }, [who])]
        .concat(BCOLS.map(function (c) { return el("td", { text: String(c[2](r)) }); })));
    }));
    var foot = el("tfoot", {}, [el("tr", {}, [el("td", {}), el("td", { "class": "l", text: "Team" })].concat(BCOLS.map(function (c) { return el("td", { text: String(c[2](tot)) }); })))]);
    return el("div", { "class": "tablewrap", tabindex: "0", role: "region", "aria-label": name + " box score, scrolls sideways" }, [
      el("table", { "class": "ptable btable" }, [el("thead", {}, [head]), body, foot])]);
  }
  function drawMatch(id) {
    stopMatch();
    var box = $("match"), g = data.games.filter(function (x) { return String(x.id) === String(id); })[0];
    box.innerHTML = "";
    if (!g) { box.appendChild(el("p", { "class": "empty", text: "This match is not on the list of ranked teams' matches." })); return; }
    var L = g.live, live = L ? L.state === "in" : g.state === "live", fin = L ? L.state === "post" : g.state === "final";
    var t = g.start ? new Date(g.start * 1000) : null;
    function side(t) { return el("span", { "class": "mside" }, [rankTag(t.rank, t.id), logo(t.id), teamA(t.id, t.name)]); }
    var title = el("h1", { "class": "mtitle" }, [side(g.away), el("span", { "class": "mv", text: " at " }), side(g.home)]);
    var status = el("p", { "class": "mstatus" }, [live ? liveTag() : null,
      el("span", { text: (live ? " " : "") + long(g.date) + (t && !isNaN(t) ? ", " + t.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }) : "") + (fin ? " · Final" : "") })]);
    var list = el("ol", { "class": "games" }, [row(g)]);
    var sets = el("div", { "class": "msets" }), boxes = el("div", { "class": "mboxes" });
    box.appendChild(title); box.appendChild(status); box.appendChild(list); box.appendChild(sets); box.appendChild(boxes);
    box.appendChild(el("p", { "class": "note" }, [W("match.note") + " ",
      el("a", { href: data.game_page + g.id, rel: "noopener", text: W("match.ncaa_link") }), "."]));

    function readSets() {
      if (!g.espn) { sets.innerHTML = ""; return Promise.resolve(); }
      return fetch(ESPN_SUMMARY + g.espn[0], { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
        var comp = d && d.header && (d.header.competitions || [])[0];
        if (!comp) return;
        var flip = g.espn[1], by = {};
        (comp.competitors || []).forEach(function (c) { by[c.homeAway] = c; });
        var away = by[flip ? "home" : "away"], home = by[flip ? "away" : "home"];
        if (!away || !home) return;
        var n = Math.max((away.linescores || []).length, (home.linescores || []).length);
        if (!n) { sets.innerHTML = ""; return; }
        var st = (comp.status || {}).type || {};
        var nowLive = st.state === "in";
        function line(c, s) {
          var ls = c.linescores || [];
          var cells = [];
          for (var i = 0; i < n; i++) {
            var mine = ls[i] ? +ls[i].displayValue : null, other = ((c === away ? home : away).linescores || [])[i];
            var won = mine != null && other && mine > +other.displayValue && (i < n - 1 || !nowLive);
            cells.push(el("td", { "class": won ? "won" : "", text: mine == null ? "" : String(mine) }));
          }
          return el("tr", {}, [el("th", { scope: "row", "class": "l" }, [el("span", { "class": "stm" }, [rankTag(s.rank, s.id), logo(s.id, "sm"), teamA(s.id, s.name)])])].concat(cells).concat([el("td", { "class": "tot", text: c.score || "0" })]));
        }
        var head = el("tr", {}, [el("th", { scope: "col", "class": "l", text: nowLive ? (st.shortDetail || "Live") : "Set" })]);
        for (var i = 1; i <= n; i++) head.appendChild(el("th", { scope: "col", text: String(i) }));
        head.appendChild(el("th", { scope: "col", text: "Sets" }));
        sets.innerHTML = "";
        sets.appendChild(el("div", { "class": "tablewrap" }, [el("table", { "class": "ptable stable" }, [el("thead", {}, [head]), el("tbody", {}, [line(away, g.away), line(home, g.home)])])]));
        if (nowLive) matchTimers.push(setTimeout(readSets, (data.live_seconds || 20) * 1000));
      }).catch(function () {});
    }
    function readBox() {
      return fetch("match/" + g.id + ".json", { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (d) {
        boxes.innerHTML = "";
        [["away", g.away], ["home", g.home]].forEach(function (p) {
          var side = p[0], s = p[1];
          boxes.appendChild(el("h2", { "class": "mteam" }, [rankTag(s.rank, s.id), logo(s.id), teamA(s.id, s.name)]));
          boxes.appendChild(boxTable(side, d[side] || [], s.name));
          var ts = (d.tsets || {})[side] || [];
          if (ts.length) boxes.appendChild(el("p", { "class": "bysets" }, ["Hitting by set: "].concat(ts.map(function (x, i) {
            return el("span", { "class": "bs" }, [el("b", { text: "Set " + (i + 1) + " " }), x[2] ? hitFmt((x[0] - x[1]) / x[2]) : "–", el("small", { text: " (" + x[0] + "–" + x[1] + "–" + x[2] + ")" })]);
          }))));
        });
        if (d.status && d.status !== "F" && (live || !fin)) matchTimers.push(setTimeout(readBox, 60 * 1000));
      }).catch(function () {
        boxes.innerHTML = "";
        boxes.appendChild(el("p", { "class": "empty", text: live ? "Player stats appear here within about 15 minutes of the first serve." :
          fin ? "The box score has not come in yet. It usually arrives within the hour." : "Player stats appear here once the match starts." }));
        if (live || fin) matchTimers.push(setTimeout(readBox, 60 * 1000));
      });
    }
    readSets(); readBox();
  }

  // ---- a team's page: its matches, its stats and its players ----
  var TSTATS = [   // key, label, format, higher is better
    ["hit", "Hitting", hitFmt, 1], ["opp_hit", "Opponents' hitting", hitFmt, 0], ["k_set", "Kills per set", fmt.d2, 1],
    ["opp_k_set", "Opponents' kills per set", fmt.d2, 0], ["ast_set", "Assists per set", fmt.d2, 1], ["sa_set", "Aces per set", fmt.d2, 1],
    ["se_set", "Service errors per set", fmt.d2, 0], ["blk_set", "Blocks per set", fmt.d2, 1], ["d_set", "Digs per set", fmt.d2, 1],
    ["re_pct", "Reception error rate", function (v) { return v.toFixed(1) + "%"; }, 0]
  ];
  var TPCOLS = ["rank", "name", "pos", "sp", "impact_set", "k_set", "hit", "ast_set", "ace_set", "d_set", "blk_set"];
  function drawTeam(id) {
    var box = $("team");
    box.innerHTML = "";
    var t = rankOf(id);
    var mine = data.games.filter(function (g) { return g.away.id === id || g.home.id === id; });
    var which = t ? scope : "d1";            // an unranked team is measured against all of Division I
    var name = t ? t.name : (mine.length ? (mine[0].away.id === id ? mine[0].away.name : mine[0].home.name) : id);
    var goat = ((data.goat || {}).top || []).filter(function (x) { return x.id === id; })[0];
    var bits = [];
    if (t && t.record) bits.push(t.record);
    bits.push(t ? "No. " + t.rank + " in the " + data.poll.name : "Not ranked in the " + data.poll.name);
    if (goat) bits.push("No. " + goat.rank + " in the GOAT ranking");
    box.appendChild(el("div", { "class": "thead" }, [logo(id, "big"), el("div", {}, [el("h1", { text: name }), el("p", { "class": "tsub", text: bits.join(" · ") })])]));
    box.appendChild(el("div", { "class": "nav filters" }, [scopeSwitch(function () { drawTeam(id); }, !t)]));
    if (t) box.appendChild(el("div", { "class": "tvs" }, [versus(t)]));

    // matches: the latest results and what is next
    var next = mine.filter(function (g) { return g.state !== "final" && g.date >= today; }).slice(0, 5);
    var done = mine.filter(function (g) { return g.state === "final"; }).slice(-5);
    var m = el("section", { "class": "tsec" }, [el("h2", { text: W("team.matches") })]);
    if (next.length) { m.appendChild(el("h3", { "class": "day", text: W("team.coming_up") })); m.appendChild(el("ol", { "class": "games" }, next.map(row))); }
    if (done.length) { m.appendChild(el("h3", { "class": "day", text: W("team.latest_results") })); m.appendChild(el("ol", { "class": "games" }, done.slice().reverse().map(row))); }
    if (!mine.length) m.appendChild(el("p", { "class": "empty", text: "No matches are listed for " + name + "." }));
    if (mine.length) m.appendChild(el("p", { "class": "note" }, [el("a", { href: "#/", onclick: function () { if (!t) setScope("d1"); state.team = id; }, text: "All of " + name + "'s matches this season" })]));
    box.appendChild(m);

    var stats = el("section", { "class": "tsec" }, [el("h2", { text: W("team.stats") }), el("p", { "class": "empty", text: "Loading…" })]);
    var people = el("section", { "class": "tsec" }, [el("h2", { text: W("team.players") }), el("p", { "class": "empty", text: "Loading…" })]);
    box.appendChild(stats); box.appendChild(people);
    loadTeams(which).then(function (d) {
      var row1 = d.teams.filter(function (x) { return x.id === id; })[0];
      stats.removeChild(stats.lastChild);
      if (!row1) { stats.appendChild(el("p", { "class": "empty", text: "No box scores yet." })); return; }
      var tiles = TSTATS.map(function (c) {
        var v = row1[c[0]];
        var vals = d.teams.map(function (x) { return x[c[0]]; }).filter(function (x) { return x != null; });
        var place = v == null ? null : 1 + vals.filter(function (x) { return c[3] ? x > v : x < v; }).length;
        return el("div", { "class": "tile" + (place && place <= 5 ? " top" : "") }, [el("span", { "class": "lab", text: c[1] }),
          el("b", { text: v == null ? "–" : c[2](v) }), el("span", { "class": "plc", text: place ? ordinal(place) + " of " + vals.length : "" })]);
      });
      tiles.push(el("div", { "class": "tile" }, [el("span", { "class": "lab", text: "Rating" }), el("b", { text: row1.power ? ordinal(row1.power) : "–" }), el("span", { "class": "plc", text: "in Division I, by this site's rating" })]));
      tiles.push(el("div", { "class": "tile" }, [el("span", { "class": "lab", text: "Schedule strength" }), el("b", { text: row1.sos_rank ? ordinal(row1.sos_rank) : "–" }), el("span", { "class": "plc", text: "hardest of " + d.teams.length })]));
      stats.appendChild(el("div", { "class": "tiles" }, tiles));
      stats.appendChild(el("p", { "class": "note", text: row1.w + "-" + row1.l + " in matches, " + row1.sw + "-" + row1.sl + " in sets. Per-set stats from " + row1.matches + " box scores; places are among " + (which === "d1" ? "all " + d.teams.length + " Division I teams" : "the 25 ranked teams") + ". " }));
      stats.lastChild.appendChild(el("a", { href: "#/teams", text: "All team stats" }));
    }).catch(function () {});
    loadRoster(which).then(function () {
      var list = roster.players.filter(function (p) { return p.team_id === id; }).sort(function (a, b) {
        return (a.rank || 1e6) - (b.rank || 1e6) || (val(b, "impact_set") || 0) - (val(a, "impact_set") || 0);
      });
      people.removeChild(people.lastChild);
      if (!list.length) { people.appendChild(el("p", { "class": "empty", text: "No box scores yet." })); return; }
      var cols = TPCOLS.map(function (k) { return PCOLS.filter(function (c) { return c[0] === k; })[0]; });
      var head = el("tr", {}, cols.map(function (c) { return el("th", { scope: "col", "class": c[0] === "name" ? "l" : "", title: c[2] || null }, [el("span", { "class": "th", text: c[1] })]); }));
      var body = el("tbody", {}, list.map(function (p) {
        return el("tr", { "class": p.regular ? "" : "part" }, cols.map(function (c) {
          if (c[0] === "name") return el("td", { "class": "l nm" }, [el("a", { href: "#/player/" + encodeURIComponent(p.id) }, [face(p), el("span", { text: p.name })])]);
          var v = c[3](p);
          return el("td", { "class": c[0] === "impact_set" ? "strong" : "", text: v == null ? (c[0] === "rank" ? "–" : "") : c[4](v) });
        }));
      }));
      people.appendChild(el("div", { "class": "tablewrap", tabindex: "0", role: "region", "aria-label": name + " players, scrolls sideways" }, [
        el("table", { "class": "ptable tptable" }, [el("thead", {}, [head]), body])]));
      people.appendChild(el("p", { "class": "note", text: W(which === "d1" ? "team.players_note_d1" : "team.players_note") }));
    }).catch(function () {});
  }

  function route() {
    var h = location.hash, card = /^#\/?player\/(.+)$/.exec(h), match = /^#\/?match\/(\d+)/.exec(h), tm = /^#\/?team\/(.+)$/.exec(h);
    stopMatch();
    var page = tm ? "team" : match ? "match" : card ? "card" : /^#\/?players/.test(h) ? "players" : /^#\/?rankings/.test(h) ? "rankings" : /^#\/?teams/.test(h) ? "teams" : "matches";
    ["matches", "rankings", "teams", "players", "card", "match", "team"].forEach(function (p) { $("page-" + p).hidden = p !== page; });
    Array.prototype.forEach.call(document.querySelectorAll(".pages a"), function (a) {
      if (a.dataset.page === (page === "card" ? "players" : page === "match" ? "matches" : page === "team" ? "teams" : page)) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    document.title = ({ rankings: W("rankings.title"), teams: W("teams.title"), players: W("players.title"), match: W("matches.box_score"), team: "Team", card: "Player card" }[page] || W("matches.title")) + " | " + data.site;
    if (page === "team") drawTeam(decodeURIComponent(tm[1])); else if (page === "match") drawMatch(match[1]); else if (page === "rankings") drawRanks(); else if (page === "teams") drawTeams(); else if (page === "players") drawPlayers(); else if (page === "card") drawCard(decodeURIComponent(card[1])); else draw();
    window.scrollTo(0, 0);
  }

  fetch("data.json", { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (d) {
    data = d;
    $("brand").textContent = d.site;
    Array.prototype.forEach.call(document.querySelectorAll("[data-w]"), function (n) { var s = W(n.getAttribute("data-w")); if (s) n.textContent = s; });
    $("lede").textContent = W("matches.lede", { poll: d.poll.name });
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

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

  function rankTag(rank) {
    return el("span", { "class": "rk" + (rank ? "" : " none"), text: rank ? String(rank) : "", "aria-label": rank ? "ranked " + rank : null });
  }

  // ---- the 25 ----
  function drawRanks() {
    var ol = $("ranks");
    ol.innerHTML = "";
    data.poll.teams.forEach(function (t) {
      var move = t.prev == null ? ["new", "up", "not ranked last week"] : t.prev > t.rank ? ["▲" + (t.prev - t.rank), "up", "up " + (t.prev - t.rank) + " from last week"]
        : t.prev < t.rank ? ["▼" + (t.rank - t.prev), "", "down " + (t.rank - t.prev) + " from last week"] : null;
      var b = el("button", { type: "button", "aria-pressed": String(state.team === t.id), disabled: !t.id,
        title: t.id ? "Show " + t.name + "'s whole season" : "No matches found for this team",
        onclick: function () { state.team = state.team === t.id ? null : t.id; draw(); $("matches").scrollIntoView({ block: "start", behavior: "smooth" }); } }, [
        rankTag(t.rank), el("span", { "class": "nm", text: t.name }),
        el("span", { "class": "rec" }, [t.record || "", move ? el("span", { "class": "mv " + move[1], text: move[0], "aria-label": move[2] }) : null])]);
      ol.appendChild(el("li", {}, [b]));
    });
  }

  // ---- one match ----
  function row(g) {
    var fin = g.state === "final", live = g.state === "live", scored = (fin || live) && g.away.sets != null && g.home.sets != null;
    var awayWon = fin && scored && g.away.sets > g.home.sets, homeWon = fin && scored && g.home.sets > g.away.sets;
    var t = g.start ? new Date(g.start * 1000) : null;
    var note = g.state === "other" ? (g.note ? g.note.charAt(0).toUpperCase() + g.note.slice(1) : "Not played") : "";
    var when = fin ? "Final" : note ? note : t && !isNaN(t) ? t.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }) : "Time not set";
    function team(side, s, lost) {
      var kids = [el("span", { "class": "name", text: s.name }), rankTag(s.rank)];
      if (side === "home") kids.reverse();
      return el("span", { "class": "team " + side + (lost ? " lost" : "") }, kids);
    }
    var mid = scored
      ? el("span", { "class": "mid", "aria-label": g.away.name + " " + g.away.sets + ", " + g.home.name + " " + g.home.sets }, [
          el("span", { "class": "sa " + (homeWon ? "l" : "w"), text: String(g.away.sets) }), el("span", { "class": "dash", text: "–" }),
          el("span", { "class": "sh " + (awayWon ? "l" : "w"), text: String(g.home.sets) })])
      : el("span", { "class": "mid at", text: "at" });
    var more = [];
    if (live) more.push(el("span", { "class": "live", text: "In progress " }));
    if (g.round) more.push(g.round + " ");
    if (!fin && g.watch) {
      more.push(g.watch.length ? el("span", { "class": "watch" }, [el("span", { "class": "sr", text: "Watch on " }), g.watch.join(", ")])
        : el("span", { "class": "watch none", text: "No broadcast listed" }));
    }
    if (fin || live) more.push(el("a", { href: data.game_page + g.id, text: "Box score", rel: "noopener" }));
    return el("li", { "class": "game" + (g.away.rank && g.home.rank ? " both" : "") }, [
      el("span", { "class": "when", text: when }), team("away", g.away, homeWon), mid, team("home", g.home, awayWon),
      el("span", { "class": "more" }, more)]);
  }

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
    drawRanks();
    var holder = $("list"), nav = $("nav"), head = $("h-list");
    holder.innerHTML = ""; nav.innerHTML = "";
    var weeks = {};
    data.games.forEach(function (g) { weeks[monday(g.date)] = 1; });
    var first = Object.keys(weeks).sort()[0], last = Object.keys(weeks).sort().pop();

    if (state.team) {
      var t = data.poll.teams.filter(function (x) { return x.id === state.team; })[0];
      var mine = data.games.filter(function (g) { return g.away.id === t.id || g.home.id === t.id; });
      head.textContent = "No. " + t.rank + " " + t.name + ", whole season";
      nav.appendChild(el("button", { type: "button", text: "Back to all 25", onclick: function () { state.team = null; draw(); } }));
      var next = mine.filter(function (g) { return g.state !== "final" && g.date >= today; }), done = mine.filter(function (g) { return g.state === "final" || g.date < today; });
      if (next.length) { holder.appendChild(el("p", { "class": "note", text: next.length + " still to play, " + done.length + " played." })); listInto(holder, next); }
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
    holder.appendChild(el("p", { "class": "note", text: games.length + " matches this week" + (both ? ", " + both + " of them between two ranked teams (marked with a yellow edge)" : "") +
      ". The visiting team is on the left, and the channel or streaming service is on the right for matches in the next two weeks. Numbers are this week's rankings, also for earlier weeks. Choose a team above to see its whole season." }));
  }

  fetch("data.json", { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (d) {
    data = d;
    $("brand").textContent = d.site;
    var through = short(d.poll.through);
    $("poll-date").textContent = d.poll.name + ", through matches of " + through;
    $("lede").textContent = "Every match played by a team in the " + d.poll.name + ", week by week. The rankings are checked for a new poll every Monday.";
    var u = new Date(d.updated);
    $("foot-updated").textContent = "Scores and schedule updated " + (isNaN(u) ? d.updated : u.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })) +
      ". Rankings: " + d.poll.name + " through " + day(d.poll.through).toLocaleDateString(undefined, { dateStyle: "long" }) + ".";
    draw();
  }).catch(function () {
    $("h-list").textContent = "The matches could not be loaded";
    $("list").appendChild(el("p", { "class": "empty", text: "Reload the page to try again. If this keeps happening, the nightly update may not have run yet." }));
  });
})();

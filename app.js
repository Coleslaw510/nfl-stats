(() => {
  const TABS = {
    ppg:  { label: "Points per game",          head: "Pts/G",       opp: "papg", oppLabel: "Opp pts allowed rank", legend: "Opponent defense (points allowed rank)", fmt: 1 },
    ypg:  { label: "Yards per game",           head: "Yds/G",       opp: "yapg", oppLabel: "Opp yds allowed rank", legend: "Opponent defense (yards allowed rank)",  fmt: 1 },
    papg: { label: "Points allowed per game",  head: "Pts allowed/G", opp: "ppg", oppLabel: "Opp points/G rank",  legend: "Opponent offense (points per game rank)", fmt: 1 },
    yapg: { label: "Yards allowed per game",   head: "Yds allowed/G", opp: "ypg", oppLabel: "Opp yards/G rank",   legend: "Opponent offense (yards per game rank)",  fmt: 1 },
  };
  let data, byAbbr = {}, tab = "ppg";
  const open = new Set();
  const $ = (s) => document.querySelector(s);

  // Opponent rank 1 is always the toughest matchup (best opposing unit) -> red; 32 -> green.
  function rankColor(r, n) {
    const t = Math.min(1, Math.max(0, (r - 1) / ((n || 32) - 1)));
    const hue = t * 120;                    // 0 red -> 60 yellow -> 120 green
    const light = 78 - Math.sin(t * Math.PI) * 4;
    return `hsl(${hue.toFixed(0)} 70% ${light.toFixed(0)}%)`;
  }
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmtDate = (iso) => new Date(iso).toLocaleDateString(undefined, { weekday: "short", month: "numeric", day: "numeric" });

  function record(t) {
    let w = 0, l = 0, d = 0;
    t.schedule.forEach((g) => { if (g.final) g.result === "W" ? w++ : g.result === "L" ? l++ : d++; });
    return d ? `${w}-${l}-${d}` : `${w}-${l}`;
  }

  function schedHTML(t) {
    const cfg = TABS[tab], n = data.teams.length;
    const rows = t.schedule.map((g) => {
      if (g.bye) return `<tr class="bye"><td class="wk">${g.week}</td><td colspan="3">Bye</td></tr>`;
      const o = byAbbr[g.opp];
      const ha = g.neutral ? "vs" : g.home ? "vs" : "@";
      let res;
      if (g.final) res = `<span class="${g.result}">${g.result}</span> ${g.pf}–${g.pa}`;
      else if (g.state === "in") res = `<span class="live">Live</span> ${g.pf ?? ""}–${g.pa ?? ""}`;
      else res = `<span class="up">${fmtDate(g.date)}</span>`;
      let pill = "";
      if (o && o.rank[cfg.opp] != null) {
        const r = o.rank[cfg.opp];
        pill = `<span class="pill" style="background:${rankColor(r, n)}" title="${esc(o.name)}: #${r} in ${esc(TABS[cfg.opp].label.toLowerCase())} (${o[cfg.opp]})">${r}</span><span class="oval">${o[cfg.opp].toFixed(1)}</span>`;
      }
      return `<tr class="${g.final ? "played" : ""}">
        <td class="wk">${g.week}</td>
        <td class="opp"><span class="ha">${ha}</span>${o && o.logo ? `<img src="${esc(o.logo)}" alt="" loading="lazy">` : ""}${esc(g.opp)}${g.neutral ? ' <span class="muted small">(N)</span>' : ""}</td>
        <td class="res">${res}</td>
        <td class="orank">${pill}</td></tr>`;
    }).join("");
    return `<table><thead><tr><th>Wk</th><th>Opponent</th><th>Result</th><th class="orank">${esc(cfg.oppLabel)}</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  function render() {
    const cfg = TABS[tab];
    document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === tab));
    $("#value-head").textContent = cfg.head;
    $("#legend-label").textContent = cfg.legend + " — 1 = best unit";
    const teams = [...data.teams].sort((a, b) => (a.rank[tab] ?? 99) - (b.rank[tab] ?? 99) || a.name.localeCompare(b.name));
    $("#list").innerHTML = teams.map((t) => {
      const v = t[tab];
      return `<li class="${open.has(t.abbr) ? "open" : ""}" data-abbr="${t.abbr}">
        <button class="row" aria-expanded="${open.has(t.abbr)}">
          <span class="rank">${t.rank[tab] ?? "–"}</span>
          <span class="team">${t.logo ? `<img src="${esc(t.logo)}" alt="" loading="lazy">` : ""}<span class="nm">${esc(t.name)} <span class="rec">${record(t)}</span></span></span>
          <span class="val">${v == null ? "–" : v.toFixed(cfg.fmt)}<small>${t.gp} G</small></span>
          <span class="chev" aria-hidden="true"></span>
        </button>
        <div class="sched">${open.has(t.abbr) ? schedHTML(t) : ""}</div>
      </li>`;
    }).join("");
  }

  function setTab(t) { if (TABS[t]) { tab = t; history.replaceState(null, "", "#" + t + (open.size ? "/" + [...open].join(",") : "")); render(); } }

  document.querySelector(".tabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) setTab(b.dataset.tab); });
  $("#list").addEventListener("click", (e) => {
    const li = e.target.closest("li"); if (!li || !e.target.closest(".row")) return;
    const a = li.dataset.abbr;
    open.has(a) ? open.delete(a) : open.add(a);
    li.classList.toggle("open", open.has(a));
    li.querySelector(".row").setAttribute("aria-expanded", open.has(a));
    li.querySelector(".sched").innerHTML = open.has(a) ? schedHTML(byAbbr[a]) : "";
    history.replaceState(null, "", "#" + tab + (open.size ? "/" + [...open].join(",") : ""));
  });

  fetch("data.json", { cache: "no-cache" }).then((r) => r.json()).then((d) => {
    data = d;
    d.teams.forEach((t) => (byAbbr[t.abbr] = t));
    $("#season").textContent = d.season + " regular season";
    const asof = new Date(d.generated_utc).toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" });
    let s = `Data as of ${asof} · through Week ${d.through_week}`;
    if (d.pending_games_in_week && d.pending_games_in_week.length) s += ` (not yet final: ${d.pending_games_in_week.join(", ")})`;
    $("#asof").textContent = s;
    const [h, sel] = location.hash.slice(1).split("/");
    if (TABS[h]) tab = h;
    if (sel) sel.split(",").forEach((a) => byAbbr[a] && open.add(a));
    render();
  }).catch((err) => { $("#asof").textContent = "Could not load data.json — serve this folder over HTTP (python3 -m http.server). " + err; });
})();

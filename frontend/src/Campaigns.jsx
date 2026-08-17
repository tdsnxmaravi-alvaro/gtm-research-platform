import React, { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

const STAGES = ["research", "consolidate", "enrich", "outreach"];
const TIER_RANK = { A: 0, B: 1, C: 2, D: 3 };
const TERMINAL = ["done", "error", "canceled", "paused"];

function tierRank(t) {
  const r = TIER_RANK[(t || "").toUpperCase()];
  return r === undefined ? 9 : r;
}

function describe(cfg) {
  const parts = [cfg.target_type, cfg.mode];
  const perRow =
    cfg.provided_column_overrides &&
    Object.values(cfg.provided_column_overrides).includes("country");
  parts.push(perRow ? "per-row country" : cfg.country || "no country");
  if (cfg.vendor) parts.push(cfg.vendor);
  const enr = cfg.enrichment || {};
  parts.push(enr.want && enr.want !== "none" ? `${enr.provider} ${enr.want}` : "no enrich");
  if (cfg.process_limit) parts.push(`limit ${cfg.process_limit}`);
  if (cfg.outreach?.enabled) {
    const tiers = cfg.outreach.tiers;
    parts.push(`outreach ${tiers && tiers.length ? tiers.join("/") : "≥" + cfg.outreach.min_tier}`);
  }
  return parts.join(" · ");
}

export default function Campaigns({ onEdit }) {
  const [campaigns, setCampaigns] = useState([]);
  const [runs, setRuns] = useState({}); // campaignId -> latest run
  const [stageRuns, setStageRuns] = useState({}); // campaignId -> { stage: run }
  const [results, setResults] = useState({}); // campaignId -> rows
  const [resultsOpen, setResultsOpen] = useState({}); // campaignId -> bool
  const [confirmDel, setConfirmDel] = useState(null); // campaign pending delete
  const [confirmRelaunch, setConfirmRelaunch] = useState(null); // campaign pending relaunch
  const [relaunchInfo, setRelaunchInfo] = useState(null); // summary for the modal
  const [error, setError] = useState("");
  const pollTimers = useRef({});
  const alive = useRef(true);

  function clearPoll(id) {
    const t = pollTimers.current[id];
    if (t != null) {
      clearInterval(t);
      delete pollTimers.current[id];
    }
  }

  function setPoll(id, tick) {
    clearPoll(id);
    pollTimers.current[id] = setInterval(tick, 2000);
  }

  async function refreshStages(id) {
    try {
      const data = await api.campaignRuns(id);
      if (!alive.current) return;
      setStageRuns((s) => ({ ...s, [id]: data }));
    } catch {
      /* ignore */
    }
  }

  async function load() {
    try {
      const data = await api.listCampaigns();
      if (!alive.current) return;
      const list = data.results || data;
      setCampaigns(list);
      // Fetch the latest run for each campaign so the card shows the last summary.
      list.forEach(async (c) => {
        try {
          const run = await api.campaignStatus(c.id);
          if (!alive.current) return;
          if (run && run.id) setRuns((r) => ({ ...r, [c.id]: run }));
        } catch {
          /* ignore */
        }
        if (alive.current) refreshStages(c.id);
      });
    } catch (e) {
      if (alive.current) setError(String(e.message || e));
    }
  }
  useEffect(() => {
    alive.current = true;
    load();
    return () => {
      alive.current = false;
      Object.values(pollTimers.current).forEach(clearInterval);
      pollTimers.current = {};
    };
  }, []);

  function lastStage(config) {
    if (config?.outreach?.enabled) return "outreach";
    if (config?.enrichment?.want && config.enrichment.want !== "none") return "enrich";
    return "consolidate";
  }

  function pollPipeline(id, config) {
    const last = lastStage(config);
    setPoll(id, async () => {
      try {
        const run = await api.campaignStatus(id);
        if (!alive.current) return;
        setRuns((r) => ({ ...r, [id]: run }));
        refreshStages(id);
        const terminal =
          ["error", "canceled", "paused"].includes(run.status) ||
          (run.stage === last && run.status === "done");
        if (terminal) clearPoll(id);
      } catch {
        clearPoll(id);
      }
    });
  }

  async function start(id, config) {
    // Optimistic: reflect "running" immediately so Start disables and Pause/Stop enable.
    setRuns((r) => ({ ...r, [id]: { status: "pending", stage: "research", processed: 0, total: 0 } }));
    setStageRuns((s) => ({ ...s, [id]: { ...(s[id] || {}), research: { stage: "research", status: "pending" } } }));
    try {
      await api.start(id);
      pollPipeline(id, config);
    } catch (e) {
      setError(String(e.message || e));
    }
  }
  const pause = (id) => stopOrPause(id, api.pause);
  const stop = (id) => stopOrPause(id, api.stop);

  async function stopOrPause(id, fn) {
    try {
      await fn(id);
      // Refresh so the button flips to Resume even without an active poll (e.g. the
      // worker already died and the run was left 'running').
      const run = await api.campaignStatus(id);
      setRuns((r) => ({ ...r, [id]: run }));
      refreshStages(id);
    } catch (e) {
      setError(String(e.message || e));
    }
  }

  async function startStage(id, stage) {
    try {
      const run = await api.runStage(id, stage);
      setRuns((r) => ({ ...r, [id]: run }));
      poll(run.id, id);
    } catch (e) {
      setError(String(e.message || e));
    }
  }

  function poll(runId, campaignId) {
    setPoll(campaignId, async () => {
      try {
        const run = await api.getRun(runId);
        if (!alive.current) return;
        setRuns((r) => ({ ...r, [campaignId]: run }));
        refreshStages(campaignId);
        if (TERMINAL.includes(run.status)) clearPoll(campaignId);
      } catch {
        clearPoll(campaignId);
      }
    });
  }

  async function toggleResults(id) {
    if (resultsOpen[id]) {
      setResultsOpen((o) => ({ ...o, [id]: false }));
      return;
    }
    if (!results[id]) {
      try {
        const data = await api.results(id);
        setResults((r) => ({ ...r, [id]: data.results || [] }));
      } catch (e) {
        setError(String(e.message || e));
        return;
      }
    }
    setResultsOpen((o) => ({ ...o, [id]: true }));
  }

  async function doDelete() {
    const c = confirmDel;
    setConfirmDel(null);
    if (!c) return;
    try {
      await api.deleteCampaign(c.id);
      setCampaigns((cs) => cs.filter((x) => x.id !== c.id));
    } catch (e) {
      setError(String(e.message || e));
    }
  }

  async function askRelaunch(c) {
    setConfirmRelaunch(c);
    setRelaunchInfo(null);
    try {
      setRelaunchInfo(await api.relaunchSummary(c.id));
    } catch (e) {
      setError(String(e.message || e));
    }
  }

  async function doRelaunch() {
    const c = confirmRelaunch;
    setConfirmRelaunch(null);
    setRelaunchInfo(null);
    if (!c) return;
    // Optimistic: reflect "running" immediately so the controls flip.
    setRuns((r) => ({ ...r, [c.id]: { status: "pending", stage: "research", processed: 0, total: 0 } }));
    setStageRuns((s) => ({ ...s, [c.id]: { research: { stage: "research", status: "pending" } } }));
    try {
      await api.relaunch(c.id);
      pollPipeline(c.id, c.config);
    } catch (e) {
      setError(String(e.message || e));
    }
  }

  if (error) return <p className="error">{error}</p>;
  if (!campaigns.length) return <p>No campaigns yet. Create one from “New campaign”.</p>;

  return (
    <div className="list">
      {campaigns.map((c) => {
        const run = runs[c.id];
        const rows = results[c.id];
        const sorted = rows
          ? [...rows].sort(
              (a, b) =>
                tierRank(a.final_tier || a.tier) - tierRank(b.final_tier || b.tier) ||
                (Number(b.score) || 0) - (Number(a.score) || 0)
            )
          : null;
        const counts = rows
          ? rows.reduce((m, r) => {
              const t = (r.final_tier || r.tier || "?").toUpperCase();
              m[t] = (m[t] || 0) + 1;
              return m;
            }, {})
          : {};
        const running = run && (run.status === "running" || run.status === "pending");
        const started = stageRuns[c.id] && Object.keys(stageRuns[c.id]).length > 0;
        const last = lastStage(c.config);
        const complete = started && stageRuns[c.id][last] && stageRuns[c.id][last].status === "done";
        const resumable = started && !running && !complete;
        return (
          <div className="card row" key={c.id}>
            <div>
              <h3>{c.name}</h3>
              <small>{describe(c.config)}</small>
            </div>
            <div className="stages">
              {!complete && !running && (
                <button className="primary" onClick={() => start(c.id, c.config)}
                        title={resumable ? "Resume the pipeline where it left off" : "Run all phases in order: research → consolidate → enrich → outreach"}>
                  {resumable ? "▶ Resume" : "▶ Start"}
                </button>
              )}
              {running && (
                <button onClick={() => pause(c.id)}
                        title="Pause after the current step — resume later with Start (e.g. if low on Apollo credits)">⏸ Pause</button>
              )}
              {running && (
                <button onClick={() => stop(c.id)}
                        title="Cancel the run. Saved progress is kept, so Start won't re-charge done companies">■ Stop</button>
              )}
              {started && (
                <button onClick={() => toggleResults(c.id)} disabled={running}
                        title="Show/hide the scored companies (sorted by tier & score)">
                  {resultsOpen[c.id] ? "results ▾" : "results ▸"}
                </button>
              )}
              {!started && onEdit && (
                <button onClick={() => onEdit(c)} title="Edit this campaign (available until it first runs)">✎ Edit</button>
              )}
              {started && !running && (
                <button onClick={() => askRelaunch(c)}
                        title="Re-run the whole pipeline from scratch (research is re-queried). Shared caches are kept so Apollo isn't re-charged for companies already enriched.">↻ Relaunch</button>
              )}
              {!running && (
                <button onClick={() => setConfirmDel(c)}
                        title="Delete (logical): hides the campaign but keeps results/contacts for future reuse">🗑 Delete</button>
              )}
              {started &&
                (running ? (
                  <span className="dl disabled" title="Available when the run finishes">⬇ Excel</span>
                ) : (
                  <a className="dl" href={`/api/campaigns/${c.id}/download/?artifact=master.xlsx`}
                     title="Download the consolidated list with contacts (Excel)">⬇ Excel</a>
                ))}
              {started &&
                (running ? (
                  <span className="dl disabled" title="Available when the run finishes">⬇ Emails</span>
                ) : (
                  <a className="dl" href={`/api/campaigns/${c.id}/download_eml/`}
                     title="Download all outreach .eml drafts as a zip">⬇ Emails</a>
                ))}
            </div>
            {running && (
              <div className={`status ${run.status}`}>
                {run.stage}: <b>{run.status}</b>
                {run.total ? ` — ${run.processed}/${run.total}` : ""}
                {run.total > 0 ? (
                  <div className="progress">
                    <div className="bar" style={{ width: `${Math.round((run.processed / run.total) * 100)}%` }} />
                  </div>
                ) : (
                  <div className="progress indeterminate"><div className="bar" /></div>
                )}
              </div>
            )}
            {stageRuns[c.id] && (
              <div className="phases">
                {STAGES.map((s) => {
                  const sr = stageRuns[c.id][s];
                  const help = {
                    research: "Score each company's fit (with evidence URLs) → tier A–D",
                    consolidate: "Dedupe + keep the qualified companies (tier ≥ min) → master",
                    enrich: "Find contacts (email/phone) for the qualified companies",
                    outreach: "Generate personalized .eml drafts",
                  }[s];
                  return (
                    <div key={s} className={`phase ${sr ? sr.status : "idle"}`} title={help}>
                      <b>{s}</b> · {sr ? sr.status : "—"}
                      {sr && sr.message ? <span className="phase-msg"> · {sr.message}</span> : null}
                    </div>
                  );
                })}
              </div>
            )}
            {started && (
              <details>
                <summary className="link">Run / re-run a single stage (research · consolidate · enrich · outreach)</summary>
                <div className="stages" style={{ marginTop: 8 }}>
                  {STAGES.map((s) => (
                    <button key={s} onClick={() => startStage(c.id, s)} disabled={running}>{s}</button>
                  ))}
                </div>
              </details>
            )}
            {resultsOpen[c.id] && rows && (
              <>
                <div className="status">
                  <b>{c.name}</b> — <b>{rows.length}</b> companies —{" "}
                  {["A", "B", "C", "D"].map((t) => (counts[t] ? `${t}:${counts[t]} ` : "")).join("")}
                  {rows.length > 50 ? "· showing top 50" : ""}
                </div>
                <div className="results-scroll">
                  <table className="results">
                    <thead>
                      <tr><th>Tier</th><th>Score</th><th>Company</th><th>Evidence</th></tr>
                    </thead>
                    <tbody>
                      {sorted.slice(0, 50).map((r, i) => (
                        <tr key={i}>
                          <td className={`tier t${(r.final_tier || r.tier || "").toUpperCase()}`}>{r.final_tier || r.tier}</td>
                          <td>{r.score}</td>
                          <td>{r.company}</td>
                          <td>{r.evidence_count}</td>
                        </tr>
                      ))}
                      {!rows.length && (
                        <tr><td colSpan={4}>No results yet — run research first.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        );
      })}
      {confirmDel && (
        <div className="modal-overlay" onClick={() => setConfirmDel(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Delete campaign</h3>
            <p>
              Delete <b>{confirmDel.name}</b>? It’s hidden from the list, but its results
              and contacts stay on disk so future campaigns can reuse them.
            </p>
            <div className="modal-actions">
              <button onClick={() => setConfirmDel(null)}>Cancel</button>
              <button className="danger" onClick={doDelete}>Delete</button>
            </div>
          </div>
        </div>
      )}
      {confirmRelaunch && (
        <div className="modal-overlay" onClick={() => { setConfirmRelaunch(null); setRelaunchInfo(null); }}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Relaunch campaign</h3>
            <p>
              Re-run <b>{confirmRelaunch.name}</b> from scratch. The <b>research phase
              runs again</b> (LARA is re-queried), and consolidate{relaunchInfo && relaunchInfo.stages?.includes("enrich") ? ", enrich" : ""}
              {relaunchInfo && relaunchInfo.stages?.includes("outreach") ? ", outreach" : ""} are rebuilt.
            </p>
            {!relaunchInfo ? (
              <p className="status">Checking what will run…</p>
            ) : relaunchInfo.uses_apollo ? (
              <div className="status error">
                <b>⚠ This campaign uses Apollo (consumes credits).</b>
                <div style={{ marginTop: 6 }}>
                  Based on the previous shortlist: <b>{relaunchInfo.apollo_new_companies}</b> new
                  {" "}compan{relaunchInfo.apollo_new_companies === 1 ? "y" : "ies"} would consume Apollo credits;
                  {" "}<b>{relaunchInfo.apollo_reused_companies}</b> already in the shared contact base (no charge).
                </div>
                <div style={{ marginTop: 6, opacity: 0.8 }}>{relaunchInfo.shortlist_note}</div>
              </div>
            ) : (
              <p className="status">
                Enrichment uses <b>{relaunchInfo.provider === "lara" ? "LARA (no credit cost)" : relaunchInfo.want === "none" ? "no enrichment" : relaunchInfo.provider}</b>.
                No Apollo credits will be consumed.
              </p>
            )}
            <div className="modal-actions">
              <button onClick={() => { setConfirmRelaunch(null); setRelaunchInfo(null); }}>Cancel</button>
              <button className="danger" onClick={doRelaunch} disabled={!relaunchInfo}>↻ Relaunch</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

import React, { useEffect, useState } from "react";
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
  const [error, setError] = useState("");

  async function refreshStages(id) {
    try {
      const data = await api.campaignRuns(id);
      setStageRuns((s) => ({ ...s, [id]: data }));
    } catch {
      /* ignore */
    }
  }

  async function load() {
    try {
      const data = await api.listCampaigns();
      const list = data.results || data;
      setCampaigns(list);
      // Fetch the latest run for each campaign so the card shows the last summary.
      list.forEach(async (c) => {
        try {
          const run = await api.campaignStatus(c.id);
          if (run && run.id) setRuns((r) => ({ ...r, [c.id]: run }));
        } catch {
          /* ignore */
        }
        refreshStages(c.id);
      });
    } catch (e) {
      setError(String(e.message || e));
    }
  }
  useEffect(() => {
    load();
  }, []);

  function lastStage(config) {
    if (config?.outreach?.enabled) return "outreach";
    if (config?.enrichment?.want && config.enrichment.want !== "none") return "enrich";
    return "consolidate";
  }

  function pollPipeline(id, config) {
    const last = lastStage(config);
    const t = setInterval(async () => {
      try {
        const run = await api.campaignStatus(id);
        setRuns((r) => ({ ...r, [id]: run }));
        refreshStages(id);
        const terminal =
          ["error", "canceled", "paused"].includes(run.status) ||
          (run.stage === last && run.status === "done");
        if (terminal) clearInterval(t);
      } catch {
        clearInterval(t);
      }
    }, 2000);
  }

  async function start(id, config) {
    try {
      await api.start(id);
      pollPipeline(id, config);
    } catch (e) {
      setError(String(e.message || e));
    }
  }
  const pause = (id) => api.pause(id).catch((e) => setError(String(e.message || e)));
  const stop = (id) => api.stop(id).catch((e) => setError(String(e.message || e)));

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
    const t = setInterval(async () => {
      try {
        const run = await api.getRun(runId);
        setRuns((r) => ({ ...r, [campaignId]: run }));
        refreshStages(campaignId);
        if (TERMINAL.includes(run.status)) clearInterval(t);
      } catch {
        clearInterval(t);
      }
    }, 2000);
  }

  async function viewResults(id) {
    try {
      const data = await api.results(id);
      setResults((r) => ({ ...r, [id]: data.results || [] }));
    } catch (e) {
      setError(String(e.message || e));
    }
  }

  async function remove(id, name) {
    if (!window.confirm(`Delete campaign "${name}"?\nIt is hidden but its results/contacts stay on disk for future campaigns.`)) return;
    try {
      await api.deleteCampaign(id);
      setCampaigns((cs) => cs.filter((c) => c.id !== id));
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
              {!complete && (
                <button className="primary" onClick={() => start(c.id, c.config)} disabled={running}
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
                <button onClick={() => viewResults(c.id)} disabled={running}
                        title="Show the scored companies (sorted by tier & score)">results</button>
              )}
              {!started && onEdit && (
                <button onClick={() => onEdit(c)} title="Edit this campaign (available until it first runs)">✎ Edit</button>
              )}
              {!running && (
                <button onClick={() => remove(c.id, c.name)}
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
            {run && (
              <div className={`status ${run.status}`}>
                {run.stage}: <b>{run.status}</b>
                {run.total ? ` — ${run.processed}/${run.total}` : run.result_count ? ` (${run.result_count})` : ""}
                {run.message ? ` — ${run.message}` : ""}
                {running &&
                  (run.total > 0 ? (
                    <div className="progress">
                      <div className="bar" style={{ width: `${Math.round((run.processed / run.total) * 100)}%` }} />
                    </div>
                  ) : (
                    <div className="progress indeterminate"><div className="bar" /></div>
                  ))}
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
            <details>
              <summary className="link">Run a single stage (manual)</summary>
              <div className="stages" style={{ marginTop: 8 }}>
                {STAGES.map((s) => (
                  <button key={s} onClick={() => startStage(c.id, s)} disabled={running}>{s}</button>
                ))}
              </div>
            </details>
            {rows && (
              <>
                <div className="status">
                  <b>{rows.length}</b> companies —{" "}
                  {["A", "B", "C", "D"].map((t) => (counts[t] ? `${t}:${counts[t]} ` : "")).join("")}
                </div>
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
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

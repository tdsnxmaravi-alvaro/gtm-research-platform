import React, { useEffect, useState } from "react";
import { api } from "./api.js";

const STAGES = ["research", "enrich", "consolidate", "outreach"];

export default function Campaigns() {
  const [campaigns, setCampaigns] = useState([]);
  const [runs, setRuns] = useState({}); // campaignId -> latest run
  const [error, setError] = useState("");

  async function load() {
    try {
      const data = await api.listCampaigns();
      setCampaigns(data.results || data);
    } catch (e) {
      setError(String(e.message || e));
    }
  }
  useEffect(() => { load(); }, []);

  async function start(id, stage) {
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
        if (run.status === "done" || run.status === "error") clearInterval(t);
      } catch {
        clearInterval(t);
      }
    }, 2000);
  }

  if (error) return <p className="error">{error}</p>;
  if (!campaigns.length) return <p>No campaigns yet. Create one from “New campaign”.</p>;

  return (
    <div className="list">
      {campaigns.map((c) => {
        const run = runs[c.id];
        return (
          <div className="card row" key={c.id}>
            <div>
              <h3>{c.name}</h3>
              <small>{c.config.target_type} · {c.config.mode} · {c.config.country} · {c.config.vendor}</small>
            </div>
            <div className="stages">
              {STAGES.map((s) => (
                <button key={s} onClick={() => start(c.id, s)}>{s}</button>
              ))}
            </div>
            {run && (
              <div className={`status ${run.status}`}>
                {run.stage}: <b>{run.status}</b>
                {run.result_count ? ` (${run.result_count})` : ""}
                {run.message ? ` — ${run.message}` : ""}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

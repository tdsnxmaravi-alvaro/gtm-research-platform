import React, { useEffect, useState } from "react";
import { api } from "./api.js";

// Global provider catalog: toggle which research LLMs are available and pick the
// default. Enabling >1 turns campaigns into an ensemble (research runs on each,
// scores are averaged + agreement-boosted). Secrets live in .env, never here.
export default function Settings() {
  const [providers, setProviders] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(null);

  async function load() {
    try {
      const data = await api.listProviders();
      setProviders(data.results || data);
    } catch (e) {
      setError(String(e.message || e));
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function patch(p, body) {
    setBusy(p.id);
    try {
      const updated = await api.updateProvider(p.id, body);
      setProviders((ps) => ps.map((x) => (x.id === p.id ? updated : x)));
      // Default is exclusive server-side — reload to reflect the flip on others.
      if (body.is_default_research) load();
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(null);
    }
  }

  const enabledCount = providers.filter((p) => p.enabled).length;

  if (error) return <p className="error">{error}</p>;

  return (
    <div className="list">
      <div className="card">
        <h3>Research providers</h3>
        <p className="hint">
          Turn providers on/off. With <b>two or more enabled</b>, campaigns can run
          an <b>ensemble</b>: research runs on each model, scores are averaged, and
          companies found by several models get an agreement-confidence boost. Keys
          stay in <code>.env</code>.
        </p>
        {enabledCount > 1 && (
          <p className="status">Ensemble ready — {enabledCount} providers enabled.</p>
        )}
        <table className="results">
          <thead>
            <tr>
              <th>Provider</th><th>Model</th><th>Web search</th>
              <th>Key</th><th>Default</th><th>Enabled</th>
            </tr>
          </thead>
          <tbody>
            {providers.map((p) => (
              <tr key={p.id}>
                <td><b>{p.label || p.name}</b><br /><small>{p.type}</small></td>
                <td>{p.model || "—"}</td>
                <td>{p.web_search ? "yes" : "no"}</td>
                <td>
                  {p.configured ? (
                    <span className="ok">configured</span>
                  ) : (
                    <span className="warn" title={`Set ${p.api_key_env || "the API key"} in .env`}>
                      missing key
                    </span>
                  )}
                </td>
                <td>
                  <input
                    type="radio"
                    name="default-provider"
                    checked={p.is_default_research}
                    disabled={busy === p.id || !p.enabled}
                    onChange={() => patch(p, { is_default_research: true })}
                    title="Primary research provider"
                  />
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={p.enabled}
                    disabled={busy === p.id || (!p.configured && !p.enabled)}
                    onChange={(e) => patch(p, { enabled: e.target.checked })}
                    title={!p.configured ? "Add the API key in .env first" : "Available for campaigns"}
                  />
                </td>
              </tr>
            ))}
            {!providers.length && (
              <tr><td colSpan={6}>No providers.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

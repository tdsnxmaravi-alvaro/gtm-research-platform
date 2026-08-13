import React, { useEffect, useState } from "react";
import { api } from "./api.js";

const TYPES = ["azure_foundry", "azure_openai", "lara"];
const BLANK = {
  label: "", name: "", type: "azure_foundry", model: "", endpoint_url: "",
  api_key_env: "", web_search: true,
};

function slugify(s) {
  return (s || "").toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

// Global provider catalog: add/edit/remove research LLMs, toggle availability, and
// pick the default. Enabling >1 turns campaigns into an ensemble. Secrets live in
// .env (referenced by env-var name), never in the database.
export default function Settings() {
  const [providers, setProviders] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(null);
  const [form, setForm] = useState(null); // null | {…provider} (add or edit)
  const [saving, setSaving] = useState(false);

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

  async function saveForm() {
    const body = { ...form, name: form.name || slugify(form.label) };
    if (!body.name) {
      setError("A name or label is required.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      if (form.id) await api.updateProvider(form.id, body);
      else await api.createProvider(body);
      setForm(null);
      load();
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setSaving(false);
    }
  }

  async function remove(p) {
    if (!window.confirm(`Remove provider "${p.label || p.name}"?`)) return;
    setBusy(p.id);
    try {
      await api.deleteProvider(p.id);
      setProviders((ps) => ps.filter((x) => x.id !== p.id));
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(null);
    }
  }

  const enabledCount = providers.filter((p) => p.enabled).length;
  const set = (k) => (e) =>
    setForm((f) => ({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  return (
    <div className="list">
      {error && <p className="error">{error}</p>}
      <div className="card">
        <div className="row" style={{ alignItems: "center" }}>
          <h3>Research providers</h3>
          <button className="primary" onClick={() => setForm({ ...BLANK })} disabled={!!form}>
            + Add provider
          </button>
        </div>
        <p className="hint">
          Add or edit the research LLMs. With <b>two or more enabled</b>, campaigns can
          run an <b>ensemble</b>: research runs on each model, scores are averaged, and
          companies found by several models get an agreement-confidence boost. The API
          token is referenced by an <b>environment-variable name</b> and stays in{" "}
          <code>.env</code> — never in the database.
        </p>
        {enabledCount > 1 && (
          <p className="status">Ensemble ready — {enabledCount} providers enabled.</p>
        )}

        {form && (
          <div className="card" style={{ background: "#f6f8fa", marginBottom: 12 }}>
            <h4>{form.id ? "Edit provider" : "New provider"}</h4>
            <div className="grid2">
              <label className="field">
                <span className="lbl">Label</span>
                <input value={form.label} onChange={set("label")} placeholder="Azure Foundry — gpt-5.6-sol" />
              </label>
              <label className="field">
                <span className="lbl">Name (id)</span>
                <input value={form.name} onChange={set("name")}
                       placeholder={slugify(form.label) || "auto from label"}
                       disabled={!!form.id} />
              </label>
              <label className="field">
                <span className="lbl">Type</span>
                <select value={form.type} onChange={set("type")}>
                  {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
              <label className="field">
                <span className="lbl">Model / deployment</span>
                <input value={form.model} onChange={set("model")} placeholder="gpt-5.6-sol" />
              </label>
              <label className="field">
                <span className="lbl">Endpoint URL</span>
                <input value={form.endpoint_url} onChange={set("endpoint_url")}
                       placeholder="https://<project>.services.ai.azure.com/openai/v1" />
              </label>
              <label className="field">
                <span className="lbl">API key env var</span>
                <input value={form.api_key_env} onChange={set("api_key_env")}
                       placeholder="AZURE_FOUNDRY_API_KEY" />
              </label>
              <label className="chk">
                <input type="checkbox" checked={form.web_search} onChange={set("web_search")} />
                <span>Has web search</span>
              </label>
            </div>
            <p className="hint">
              Put the real token in <code>.env</code> as{" "}
              <code>{form.api_key_env || "YOUR_ENV_VAR"}=…</code> (gitignored). The value is
              never sent here.
            </p>
            <div className="modal-actions">
              <button onClick={() => setForm(null)} disabled={saving}>Cancel</button>
              <button className="primary" onClick={saveForm} disabled={saving}>
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        )}

        <table className="results">
          <thead>
            <tr>
              <th>Provider</th><th>Model</th><th>Web search</th>
              <th>Key</th><th>Default</th><th>Enabled</th><th></th>
            </tr>
          </thead>
          <tbody>
            {providers.map((p) => (
              <tr key={p.id}>
                <td><b>{p.label || p.name}</b><br /><small>{p.type} · {p.name}</small></td>
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
                <td style={{ whiteSpace: "nowrap" }}>
                  <button onClick={() => setForm({
                    id: p.id, label: p.label, name: p.name, type: p.type, model: p.model,
                    endpoint_url: p.endpoint_url || "", api_key_env: p.api_key_env || "",
                    web_search: p.web_search,
                  })} disabled={!!form} title="Edit">✎</button>
                  <button onClick={() => remove(p)} disabled={busy === p.id} title="Remove">🗑</button>
                </td>
              </tr>
            ))}
            {!providers.length && (
              <tr><td colSpan={7}>No providers yet — add one.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

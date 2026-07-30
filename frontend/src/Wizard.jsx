import React, { useState, useEffect } from "react";
import { api } from "./api.js";

const STEPS = ["Target", "Setup", "Details", "Prompt", "Enrich", "Outreach", "Review"];
const VENDORS = ["Bricsys", "DraftSight", "Novade", "Newforma", "Unity", "Trimble"];
const ALL_TIERS = ["A", "B", "C", "D"];

const emailOk = (s) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((s || "").trim());

export default function Wizard({ onCreated }) {
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [promptLoading, setPromptLoading] = useState(false);
  const [promptErr, setPromptErr] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState("");
  const [listReport, setListReport] = useState(null);
  const [f, setF] = useState({
    name: "",
    target_type: "resellers",
    mode: "provided",
    country: "Spain",
    vendor: "",
    provided_list_path: "",
    colMap: { company: "", website: "", country: "" },
    value_prop: "",
    fit_criteria: "",
    search_prompt: "",
    want: "emails",
    provider: "apollo",
    max_contacts: 3,
    outreach_enabled: true,
    tiers: ["A", "B"],
    sender_name: "",
    sender_email: "",
  });

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const setNum = (k) => (e) => setF({ ...f, [k]: Number(e.target.value) });
  const patch = (p) => setF({ ...f, ...p });
  const toggleTier = (t) =>
    setF({
      ...f,
      tiers: f.tiers.includes(t) ? f.tiers.filter((x) => x !== t) : [...f.tiers, t],
    });

  async function onUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadErr("");
    try {
      const rep = await api.uploadList(file);
      // Invert the detected mapping (raw header -> canonical) into column pickers.
      const inv = { company: "", website: "", country: "" };
      for (const [hdr, canon] of Object.entries(rep.mapping || {})) {
        if (canon in inv && !inv[canon]) inv[canon] = hdr;
      }
      setListReport(rep);
      setF((prev) => ({ ...prev, provided_list_path: rep.path, colMap: inv }));
    } catch (err) {
      setUploadErr(String(err.message || err));
    } finally {
      setUploading(false);
    }
  }

  const setCol = (field) => (e) =>
    setF({ ...f, colMap: { ...f.colMap, [field]: e.target.value } });

  // --- per-step validation (#7) ---
  function stepError(s) {
    const name = STEPS[s];
    if (name === "Setup") {
      if (!f.name.trim()) return "Campaign name is required.";
      if (!f.vendor) return "Pick a vendor.";
      if (!f.country.trim()) return "Country is required.";
      if (f.mode === "provided" && !f.provided_list_path.trim())
        return "Upload the list (or enter a server path).";
      if (f.mode === "provided" && listReport && !f.colMap.company)
        return "Map the company column.";
    }
    if (name === "Details") {
      if (!f.value_prop.trim() && !f.fit_criteria.trim())
        return "Add a value proposition or at least one fit criterion.";
    }
    if (name === "Prompt") {
      if (!f.search_prompt.trim()) return "The research prompt cannot be empty.";
    }
    if (name === "Enrich" && f.want !== "none" && f.max_contacts < 1)
      return "Max contacts must be ≥ 1.";
    if (name === "Outreach" && f.outreach_enabled) {
      if (f.tiers.length === 0) return "Select at least one tier for outreach.";
      if (!f.sender_name.trim()) return "Sender name is required for outreach.";
      if (!emailOk(f.sender_email)) return "A valid sender email is required for outreach.";
    }
    return "";
  }

  const curErr = stepError(step);
  const enrichIdx = STEPS.indexOf("Enrich");
  const priorValid = STEPS.slice(0, enrichIdx).every((_, i) => !stepError(i));
  const allValid = STEPS.every((_, i) => !stepError(i));

  const next = () => {
    if (curErr) return;
    setError("");
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
  };
  const back = () => {
    setError("");
    setStep((s) => Math.max(s - 1, 0));
  };

  const perCompany =
    f.want === "none" ? 0 : f.max_contacts * (1 + (f.want === "emails+phones" ? 8 : 0));

  const lowestTier = () => {
    const sel = ALL_TIERS.filter((t) => f.tiers.includes(t));
    return sel.length ? sel[sel.length - 1] : "B";
  };

  function buildConfig() {
    const cfg = {
      name: f.name,
      target_type: f.target_type,
      mode: f.mode,
      country: f.country,
      vendor: f.vendor,
      products: [
        {
          name: f.vendor || "Product",
          value_prop: f.value_prop,
          fit_criteria: f.fit_criteria.split("\n").map((s) => s.trim()).filter(Boolean),
          ...(f.search_prompt.trim() ? { search_prompt: f.search_prompt } : {}),
        },
      ],
      enrichment: {
        apollo: f.provider === "apollo" && f.want !== "none",
        want: f.want,
        provider: f.provider,
        max_contacts: Number(f.max_contacts),
      },
      outreach: {
        enabled: f.outreach_enabled,
        min_tier: lowestTier(),
        tiers: [...f.tiers].sort(),
        sender_name: f.sender_name,
        sender_email: f.sender_email,
      },
    };
    if (f.mode === "provided") cfg.provided_list_path = f.provided_list_path || "list.csv";
    const overrides = {};
    for (const [field, hdr] of Object.entries(f.colMap)) {
      if (hdr) overrides[hdr.trim().toLowerCase()] = field;
    }
    if (f.mode === "provided" && Object.keys(overrides).length)
      cfg.provided_column_overrides = overrides;
    return cfg;
  }

  async function submit() {
    if (!allValid) {
      setError("Please complete the required fields.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.createCampaign(f.name, buildConfig());
      onCreated();
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  async function regeneratePrompt() {
    setPromptLoading(true);
    setPromptErr("");
    try {
      const { prompt } = await api.previewPrompt(buildConfig());
      setF((prev) => ({ ...prev, search_prompt: prompt }));
    } catch (e) {
      setPromptErr(String(e.message || e));
    } finally {
      setPromptLoading(false);
    }
  }

  // Auto-fill the research prompt the first time the user reaches the Prompt step.
  useEffect(() => {
    if (STEPS[step] === "Prompt" && !f.search_prompt && !promptLoading && !promptErr) {
      regeneratePrompt();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  return (
    <div className="card">
      <ol className="steps">
        {STEPS.map((s, i) => (
          <li key={s} className={i === step ? "on" : i < step ? "done" : ""}>{s}</li>
        ))}
      </ol>

      {STEPS[step] === "Target" && (
        <section>
          <h2>What are you targeting?</h2>
          <div className="choices">
            <button
              className={f.target_type === "resellers" ? "choice on" : "choice"}
              onClick={() => setF({ ...f, target_type: "resellers" })}
            >
              <strong>Resellers</strong>
              <span>Companies that could SELL the product (channel recruitment)</span>
            </button>
            <button
              className={f.target_type === "accounts" ? "choice on" : "choice"}
              onClick={() => setF({ ...f, target_type: "accounts" })}
            >
              <strong>Accounts / leads</strong>
              <span>End-users that could BUY/USE the product (demand)</span>
            </button>
          </div>
        </section>
      )}

      {STEPS[step] === "Setup" && (
        <section className="grid">
          <label>Campaign name<input value={f.name} onChange={set("name")} placeholder="trimble-iberia" /></label>
          <label>Vendor
            <select value={f.vendor} onChange={set("vendor")}>
              <option value="">— select vendor —</option>
              {VENDORS.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
          <label>Country (fallback)
            <input value={f.country} onChange={set("country")} placeholder="Spain" />
            <small className="hint">Used when a row has no country. Per-row country comes from the uploaded list.</small>
          </label>
          <label>Mode
            <select value={f.mode} onChange={set("mode")}>
              <option value="provided">provided (I have a list)</option>
              <option value="discover">discover (find them)</option>
            </select>
          </label>
          {f.mode === "provided" && (
            <div className="field">
              <span className="lbl">Company list (.xlsx / .csv)</span>
              <input type="file" accept=".csv,.xlsx,.xlsm" onChange={onUpload} />
              {uploading && <small className="hint">Uploading & mapping columns…</small>}
              {uploadErr && <p className="error">{uploadErr}</p>}
              {f.provided_list_path && !uploading && !uploadErr && (
                <small className="hint">Loaded: {f.provided_list_path.split(/[\\/]/).pop()}</small>
              )}
              {listReport && (
                <div className="mapping">
                  <div className="mapgrid">
                    {["company", "website", "country"].map((field) => (
                      <label key={field}>
                        {field}{field === "company" ? " *" : ""}
                        <select value={f.colMap[field]} onChange={setCol(field)}>
                          <option value="">— none —</option>
                          {(listReport.raw_headers || []).filter(Boolean).map((h) => (
                            <option key={h} value={h}>{h}</option>
                          ))}
                        </select>
                      </label>
                    ))}
                  </div>
                  <small className="hint">
                    {listReport.with_company} companies · {listReport.with_website} with website
                    {f.colMap.country
                      ? " · per-row country detected (campaign country is the fallback)"
                      : " · no country column — campaign country used for all rows"}
                  </small>
                  {(listReport.warnings || []).map((w, i) => (
                    <div key={i} className="estimate warn">{w}</div>
                  ))}
                </div>
              )}
              <details>
                <summary className="link">Or enter a server path manually</summary>
                <input value={f.provided_list_path} onChange={set("provided_list_path")} placeholder="campaigns/data/list.xlsx" />
              </details>
            </div>
          )}
        </section>
      )}

      {STEPS[step] === "Details" && (
        <section className="grid">
          <label>Value proposition<textarea value={f.value_prop} onChange={set("value_prop")} rows={3} placeholder="Why this vendor fits this audience…" /></label>
          <label>Fit criteria (one per line)<textarea value={f.fit_criteria} onChange={set("fit_criteria")} rows={4} placeholder={"Sells CAD/design software\nActive construction projects"} /></label>
          <small className="hint">These feed the research prompt on the next step.</small>
        </section>
      )}

      {STEPS[step] === "Prompt" && (
        <section className="grid">
          <h2>Research prompt</h2>
          <small className="hint">
            Assembled from the vendor, target, country, fit criteria and scoring. Edit it freely — this exact text drives qualification.
            {f.mode === "provided" ? " The [[COMPANIES]] marker is replaced with your uploaded list at run time." : ""}
          </small>
          {promptLoading ? (
            <div className="estimate">Building prompt…</div>
          ) : (
            <textarea
              className="prompt-area"
              value={f.search_prompt}
              onChange={set("search_prompt")}
              rows={16}
              spellCheck={false}
            />
          )}
          {promptErr && <p className="error">{promptErr}</p>}
          <div>
            <button type="button" className="link" onClick={regeneratePrompt} disabled={promptLoading}>
              ↻ Regenerate from template (discards edits)
            </button>
          </div>
        </section>
      )}

      {STEPS[step] === "Enrich" && (
        <section className="grid">
          <h2>Enrichment</h2>
          <label>What to find
            <select value={f.want} onChange={set("want")}>
              <option value="none">none (qualify only)</option>
              <option value="emails">emails</option>
              <option value="emails+phones">emails + phones</option>
            </select>
          </label>
          {f.want !== "none" && (
            <div className="field">
              <span className="lbl">Provider</span>
              <div className="segmented">
                <button type="button" className={f.provider === "apollo" ? "on" : ""} onClick={() => patch({ provider: "apollo" })}>Apollo — verified, uses credits</button>
                <button type="button" className={f.provider === "lara" ? "on" : ""} onClick={() => patch({ provider: "lara" })}>LARA web search — no credits</button>
              </div>
            </div>
          )}
          {f.want !== "none" && (
            <label>Max contacts per company<input type="number" min="1" max="10" value={f.max_contacts} onChange={setNum("max_contacts")} /></label>
          )}
          {priorValid ? (
            <div className="estimate">
              {f.want === "none"
                ? "No enrichment."
                : f.provider === "apollo"
                ? `≈ ${perCompany} Apollo credits per company (${f.max_contacts} contacts${f.want === "emails+phones" ? " + phone reveals" : ""}).`
                : "LARA web search — no Apollo credits."}
            </div>
          ) : (
            <div className="estimate warn">Complete the earlier steps to see the credit estimate.</div>
          )}
        </section>
      )}

      {STEPS[step] === "Outreach" && (
        <section className="grid">
          <h2>Outreach</h2>
          <label className="row-inline">
            <input type="checkbox" checked={f.outreach_enabled}
                   onChange={(e) => patch({ outreach_enabled: e.target.checked })} />
            Generate .eml drafts
          </label>
          {f.outreach_enabled && (
            <>
              <div className="field">
                <span className="lbl">Draft for tiers</span>
                <div className="checks">
                  {ALL_TIERS.map((t) => (
                    <label key={t} className="chk">
                      <input type="checkbox" checked={f.tiers.includes(t)} onChange={() => toggleTier(t)} /> {t}
                    </label>
                  ))}
                </div>
              </div>
              <label>Sender name<input value={f.sender_name} onChange={set("sender_name")} placeholder="Natalia Olarte" /></label>
              <label>Sender email<input value={f.sender_email} onChange={set("sender_email")} placeholder="you@tdsynnex.com" /></label>
            </>
          )}
        </section>
      )}

      {STEPS[step] === "Review" && (
        <section>
          <h2>Review</h2>
          <ul className="summary">
            <li>Targeting <b>{f.target_type}</b>{f.vendor ? <> for <b>{f.vendor}</b></> : null} in <b>{f.country}</b>.</li>
            <li>Input: <b>{f.mode === "provided" ? "uploaded list" : "discover (find them)"}</b>.</li>
            <li>
              Enrichment:{" "}
              {f.want === "none" ? (
                <b>none (qualify only)</b>
              ) : (
                <>
                  <b>{f.provider === "apollo" ? "Apollo" : "LARA web search"}</b> — up to <b>{f.max_contacts}</b> contacts ({f.want})
                  {f.provider === "apollo" ? <> ≈ <b>{perCompany}</b> credits/company</> : null}
                </>
              )}.
            </li>
            <li>
              Outreach:{" "}
              {f.outreach_enabled ? (
                <>.eml drafts for tiers <b>{[...f.tiers].sort().join(", ") || "—"}</b> — from <b>{f.sender_name || "—"}</b> ({f.sender_email || "—"})</>
              ) : (
                <b>off</b>
              )}.
            </li>
          </ul>
          <button type="button" className="link" onClick={() => setShowRaw((v) => !v)}>
            {showRaw ? "Hide" : "Show"} advanced config
          </button>
          {showRaw && <pre className="review">{JSON.stringify(buildConfig(), null, 2)}</pre>}
        </section>
      )}

      {(error || (curErr && step > 0)) && <p className="error">{error || curErr}</p>}

      <footer className="actions">
        <button onClick={back} disabled={step === 0}>Back</button>
        {step < STEPS.length - 1 ? (
          <button className="primary" onClick={next} disabled={!!curErr} title={curErr || ""}>Next</button>
        ) : (
          <button className="primary" onClick={submit} disabled={busy || !allValid}>
            {busy ? "Creating…" : "Create campaign"}
          </button>
        )}
      </footer>
    </div>
  );
}

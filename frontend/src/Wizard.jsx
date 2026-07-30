import React, { useState } from "react";
import { api } from "./api.js";

const STEPS = ["Target", "Setup", "Details", "Enrich", "Outreach", "Review"];
const VENDORS = ["Bricsys", "DraftSight", "Novade", "Newforma", "Unity", "Trimble"];
const ALL_TIERS = ["A", "B", "C", "D"];

const emailOk = (s) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((s || "").trim());

export default function Wizard({ onCreated }) {
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [f, setF] = useState({
    name: "",
    target_type: "resellers",
    mode: "provided",
    country: "Spain",
    vendor: "",
    provided_list_path: "",
    value_prop: "",
    fit_criteria: "",
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

  // --- per-step validation (#7) ---
  function stepError(s) {
    if (s === 1) {
      if (!f.name.trim()) return "Campaign name is required.";
      if (!f.vendor) return "Pick a vendor.";
      if (!f.country.trim()) return "Country is required.";
      if (f.mode === "provided" && !f.provided_list_path.trim())
        return "Provide the list path (or upload the list).";
    }
    if (s === 2) {
      if (!f.value_prop.trim() && !f.fit_criteria.trim())
        return "Add a value proposition or at least one fit criterion.";
    }
    if (s === 3 && f.want !== "none" && f.max_contacts < 1)
      return "Max contacts must be ≥ 1.";
    if (s === 4 && f.outreach_enabled) {
      if (f.tiers.length === 0) return "Select at least one tier for outreach.";
      if (!f.sender_name.trim()) return "Sender name is required for outreach.";
      if (!emailOk(f.sender_email)) return "A valid sender email is required for outreach.";
    }
    return "";
  }

  const curErr = stepError(step);
  const priorValid = [0, 1, 2, 3].every((s) => !stepError(s));
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

  return (
    <div className="card">
      <ol className="steps">
        {STEPS.map((s, i) => (
          <li key={s} className={i === step ? "on" : i < step ? "done" : ""}>{s}</li>
        ))}
      </ol>

      {step === 0 && (
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

      {step === 1 && (
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
            <label>Provided list path<input value={f.provided_list_path} onChange={set("provided_list_path")} placeholder="campaigns/data/list.xlsx" /></label>
          )}
        </section>
      )}

      {step === 2 && (
        <section className="grid">
          <label>Value proposition<textarea value={f.value_prop} onChange={set("value_prop")} rows={3} placeholder="Why this vendor fits this audience…" /></label>
          <label>Fit criteria (one per line)<textarea value={f.fit_criteria} onChange={set("fit_criteria")} rows={4} placeholder={"Sells CAD/design software\nActive construction projects"} /></label>
          <small className="hint">These feed the research prompt. The vendor-driven prompt builder is coming (#12).</small>
        </section>
      )}

      {step === 3 && (
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

      {step === 4 && (
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

      {step === 5 && (
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

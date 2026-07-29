import React, { useState } from "react";
import { api } from "./api.js";

const STEPS = ["Target", "Setup", "Product", "Enrich", "Outreach", "Review"];

export default function Wizard({ onCreated }) {
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({
    name: "",
    target_type: "resellers",
    mode: "provided",
    country: "Spain",
    vendor: "",
    provided_list_path: "",
    product_name: "",
    value_prop: "",
    fit_criteria: "",
    want: "emails",
    provider: "apollo",
    max_contacts: 3,
    outreach_enabled: true,
    min_tier: "B",
    sender_name: "",
    sender_email: "",
  });

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const setNum = (k) => (e) => setF({ ...f, [k]: Number(e.target.value) });
  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const back = () => setStep((s) => Math.max(s - 1, 0));

  const perCompany =
    f.want === "none" ? 0 : f.max_contacts * (1 + (f.want === "emails+phones" ? 8 : 0));

  function buildConfig() {
    const cfg = {
      name: f.name,
      target_type: f.target_type,
      mode: f.mode,
      country: f.country,
      vendor: f.vendor,
      products: [
        {
          name: f.product_name,
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
        min_tier: f.min_tier,
        sender_name: f.sender_name,
        sender_email: f.sender_email,
      },
    };
    if (f.mode === "provided") cfg.provided_list_path = f.provided_list_path || "list.csv";
    return cfg;
  }

  async function submit() {
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
              onClick={() => setF({ ...f, target_type: "accounts", mode: f.mode })}
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
          <label>Vendor<input value={f.vendor} onChange={set("vendor")} placeholder="Trimble" /></label>
          <label>Country<input value={f.country} onChange={set("country")} placeholder="Spain" /></label>
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
          <label>Product name<input value={f.product_name} onChange={set("product_name")} placeholder="Trimble AEC portfolio" /></label>
          <label>Value proposition<textarea value={f.value_prop} onChange={set("value_prop")} rows={3} /></label>
          <label>Fit criteria (one per line)<textarea value={f.fit_criteria} onChange={set("fit_criteria")} rows={4} /></label>
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
          <label>Provider
            <select value={f.provider} onChange={set("provider")}>
              <option value="apollo">Apollo (verified emails/phones, credits)</option>
              <option value="lara">LARA web search (no Apollo credits)</option>
            </select>
          </label>
          <label>Max contacts per company<input type="number" min="1" max="10" value={f.max_contacts} onChange={setNum("max_contacts")} /></label>
          <div className="estimate">
            {f.want === "none"
              ? "No enrichment."
              : `≈ ${perCompany} Apollo credits per company (${f.max_contacts} contacts${f.want === "emails+phones" ? " + phone reveals" : ""}).`}
          </div>
        </section>
      )}

      {step === 4 && (
        <section className="grid">
          <h2>Outreach</h2>
          <label className="row-inline">
            <input type="checkbox" checked={f.outreach_enabled}
                   onChange={(e) => setF({ ...f, outreach_enabled: e.target.checked })} />
            Generate .eml drafts
          </label>
          <label>Only for tiers ≥
            <select value={f.min_tier} onChange={set("min_tier")}>
              <option value="A">A</option>
              <option value="B">B</option>
              <option value="C">C</option>
            </select>
          </label>
          <label>Sender name<input value={f.sender_name} onChange={set("sender_name")} placeholder="Name for the signature" /></label>
          <label>Sender email<input value={f.sender_email} onChange={set("sender_email")} placeholder="you@tdsynnex.com" /></label>
        </section>
      )}

      {step === 5 && (
        <section>
          <h2>Review</h2>
          <pre className="review">{JSON.stringify(buildConfig(), null, 2)}</pre>
        </section>
      )}

      {error && <p className="error">{error}</p>}

      <footer className="actions">
        <button onClick={back} disabled={step === 0}>Back</button>
        {step < STEPS.length - 1 ? (
          <button className="primary" onClick={next}>Next</button>
        ) : (
          <button className="primary" onClick={submit} disabled={busy}>
            {busy ? "Creating…" : "Create campaign"}
          </button>
        )}
      </footer>
    </div>
  );
}

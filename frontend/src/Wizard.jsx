import React, { useState } from "react";
import { api } from "./api.js";

const STEPS = ["Target", "Setup", "Product", "Review"];

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
  });

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const back = () => setStep((s) => Math.max(s - 1, 0));

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

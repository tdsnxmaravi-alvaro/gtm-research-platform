import React, { useState, useEffect } from "react";
import { api } from "./api.js";

const STEPS = ["Target", "Setup", "Prompt", "Enrich", "Outreach", "Review"];
const VENDORS = ["Bricsys", "DraftSight", "Newforma", "Novade", "Trimble", "Unity"];
const ALL_TIERS = ["A", "B", "C", "D"];

const emailOk = (s) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((s || "").trim());

function tiersFromMin(min) {
  const i = ALL_TIERS.indexOf((min || "B").toUpperCase());
  return i >= 0 ? ALL_TIERS.slice(0, i + 1) : ["A", "B"];
}

// Rebuild the wizard form state from a stored CampaignConfig (edit mode).
function hydrate(cfg) {
  const p0 = (cfg.products && cfg.products[0]) || {};
  const o = cfg.outreach || {};
  const enr = cfg.enrichment || {};
  const colMap = { company: "", website: "", country: "" };
  for (const [hdr, canon] of Object.entries(cfg.provided_column_overrides || {})) {
    if (canon in colMap && !colMap[canon]) colMap[canon] = hdr;
  }
  const limit = cfg.process_limit || 0;
  return {
    name: cfg.name || "",
    target_type: cfg.target_type || "resellers",
    mode: cfg.mode || "provided",
    country: cfg.country || "",
    countries: cfg.countries || [],
    vendor: cfg.vendor || "",
    verticals: (cfg.verticals || []).map((v) => v.slug).filter(Boolean),
    provided_list_path: cfg.provided_list_path || "",
    colMap,
    providers:
      cfg.research_providers && cfg.research_providers.length
        ? cfg.research_providers
        : cfg.research_provider
        ? [cfg.research_provider]
        : [],
    value_prop: p0.value_prop || "",
    fit_criteria: (p0.fit_criteria || []).join("\n"),
    search_prompt: p0.search_prompt || "",
    want: enr.want || "emails",
    provider: enr.provider || "apollo",
    max_contacts: enr.max_contacts || 3,
    outreach_enabled: o.enabled !== undefined ? o.enabled : true,
    tiers: o.tiers && o.tiers.length ? o.tiers : tiersFromMin(o.min_tier),
    sender_name: o.sender_name || "",
    sender_email: o.sender_email || "",
    logo_path: o.logo_path || "",
    outreach_language: o.language || "",
    limit,
    limitSel: limit ? "custom" : "all",
  };
}

export default function Wizard({ onCreated, initialConfig = null, campaignId = null }) {
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [promptLoading, setPromptLoading] = useState(false);
  const [promptErr, setPromptErr] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState("");
  const [listReport, setListReport] = useState(null);
  const [remapping, setRemapping] = useState(false);
  const [logoUrl, setLogoUrl] = useState("");
  const [dims, setDims] = useState({ universal: [], specific: [] });
  const [vtree, setVtree] = useState(null);
  const [ctree, setCtree] = useState(null);
  const [provCatalog, setProvCatalog] = useState([]);
  const [previewVertical, setPreviewVertical] = useState("");
  const [emailPreview, setEmailPreview] = useState({ html: "", source: "", loading: false });
  const [f, setF] = useState(() =>
    initialConfig
      ? hydrate(initialConfig)
      : {
          name: "",
          target_type: "resellers",
          mode: "provided",
          country: "",
          countries: [],
          vendor: "",
          verticals: [],
          provided_list_path: "",
          colMap: { company: "", website: "", country: "" },
          providers: [],
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
          logo_path: "",
          outreach_language: "",
          limit: 0,
          limitSel: "all",
        }
  );

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const setNum = (k) => (e) => setF({ ...f, [k]: Number(e.target.value) });
  const patch = (p) => setF({ ...f, ...p });
  // Changing the vendor invalidates the vendor-driven prompt, criteria + preview.
  const onVendor = (e) => {
    setF({ ...f, vendor: e.target.value, search_prompt: "", value_prop: "", fit_criteria: "", verticals: [] });
    setDims({ universal: [], specific: [] });
    setVtree(null);
    setEmailPreview({ html: "", source: "", loading: false });
  };
  const toggleVertical = (slug) =>
    setF((prev) => ({
      ...prev,
      verticals: prev.verticals.includes(slug)
        ? prev.verticals.filter((x) => x !== slug)
        : [...prev.verticals, slug],
    }));
  const toggleProvider = (name) =>
    setF((prev) => ({
      ...prev,
      providers: prev.providers.includes(name)
        ? prev.providers.filter((x) => x !== name)
        : [...prev.providers, name],
    }));
  const toggleCountry = (c) =>
    setF((prev) => ({
      ...prev,
      countries: prev.countries.includes(c)
        ? prev.countries.filter((x) => x !== c)
        : [...prev.countries, c],
    }));
  const toggleRegion = (list) =>
    setF((prev) => {
      const allOn = list.every((c) => prev.countries.includes(c));
      const set = new Set(prev.countries);
      list.forEach((c) => (allOn ? set.delete(c) : set.add(c)));
      return { ...prev, countries: [...set] };
    });
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

  const setCol = (field) => (e) => {
    const colMap = { ...f.colMap, [field]: e.target.value };
    setF({ ...f, colMap });
    // Re-inspect the list with the manual picks so the company/website counts
    // and warnings update live (the auto/AI mapping may have missed the columns).
    if (f.provided_list_path) {
      setRemapping(true);
      api
        .remapList(f.provided_list_path, colMap)
        .then((rep) => setListReport(rep))
        .catch((err) => setUploadErr(String(err.message || err)))
        .finally(() => setRemapping(false));
    }
  };

  async function onLogoUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setLogoUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(file);
    });
    setUploading(true);
    setUploadErr("");
    try {
      const rep = await api.uploadLogo(file);
      setF((prev) => ({ ...prev, logo_path: rep.path }));
    } catch (err) {
      setUploadErr(String(err.message || err));
    } finally {
      setUploading(false);
    }
  }

  // --- per-step validation (#7) ---
  function stepError(s) {
    const name = STEPS[s];
    if (name === "Setup") {
      if (!f.name.trim()) return "Campaign name is required.";
      if (!f.vendor) return "Pick a vendor.";
      const hasRowCountry = f.mode === "provided" && !!f.colMap.country;
      if (f.mode === "provided" && !hasRowCountry && !f.country.trim())
        return "Country is required (used as the fallback when a row has none).";
      if (f.mode === "provided" && f.provided_list_path.trim() === "")
        return "Upload the list (or enter a server path).";
      if (f.mode === "provided" && listReport && !f.colMap.company)
        return "Map the company column.";
      if (f.mode === "discover" && vtree && f.verticals.length === 0)
        return "Select at least one reseller vertical.";
      if (f.mode === "discover" && ctree && f.countries.length === 0)
        return "Select at least one country.";
    }
    if (name === "Prompt") {
      if (!f.search_prompt.trim()) return "The research prompt cannot be empty.";
    }
    if (name === "Enrich" && f.want !== "none" && f.max_contacts < 1)
      return "Max contacts must be ≥ 1.";
    if (name === "Outreach" && f.outreach_enabled) {
      if (f.tiers.length === 0) return "Select at least one tier for outreach.";
      if (f.sender_email.trim() && !emailOk(f.sender_email))
        return "Sender email looks invalid.";
    }
    return "";
  }

  const curErr = stepError(step);
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
  const goTo = (i) => {
    if (i === step) return;
    if (i < step) { setError(""); setStep(i); return; }      // back: always allowed
    for (let k = step; k < i; k++) if (stepError(k)) return;  // forward: require valid
    setError(""); setStep(i);
  };
  const onLimitSel = (e) => {
    const v = e.target.value;
    patch({ limitSel: v, limit: v === "custom" ? (f.limit || 20) : v === "all" ? 0 : Number(v) });
  };

  const wantEmail = f.want !== "none";
  const wantPhone = f.want === "emails+phones";
  const toggleEmail = (e) => {
    const on = e.target.checked;
    patch({ want: on ? (wantPhone ? "emails+phones" : "emails") : "none" });
  };
  const togglePhone = (e) => {
    const on = e.target.checked;
    patch({ want: on ? "emails+phones" : (wantEmail ? "emails" : "none") });
  };

  const perCompany =
    f.want === "none" ? 0 : f.max_contacts * (1 + (f.want === "emails+phones" ? 8 : 0));

  // Companies the run will actually process (respects the limit + the uploaded list).
  const listCount = listReport?.with_company || 0;
  const effectiveCount =
    f.limit > 0 ? (listCount ? Math.min(f.limit, listCount) : f.limit) : listCount;
  const totalCredits = perCompany * effectiveCount;

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
          ...(f.search_prompt.trim() && !(f.mode === "discover" && f.verticals.length > 0)
            ? { search_prompt: f.search_prompt }
            : {}),
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
        ...(f.logo_path ? { logo_path: f.logo_path } : {}),
        ...(f.outreach_language ? { language: f.outreach_language } : {}),
      },
    };
    if (f.mode === "provided") cfg.provided_list_path = f.provided_list_path || "list.csv";
    if (f.mode === "discover" && f.countries.length) cfg.countries = f.countries;
    if (f.mode === "discover" && vtree && vtree.tiers) {
      const all = [
        ...(vtree.tiers.core || []),
        ...(vtree.tiers.secondary || []),
        ...(vtree.tiers.defer || []),
      ];
      const bySlug = Object.fromEntries(all.map((v) => [v.slug, v]));
      const picked = f.verticals.map((s) => bySlug[s]).filter(Boolean);
      if (picked.length)
        cfg.verticals = picked.map((v) => ({
          name: v.name,
          slug: v.slug,
          focus: v.focus,
          example_software: v.example_software || [],
        }));
    }
    const overrides = {};
    for (const [field, hdr] of Object.entries(f.colMap)) {
      if (hdr) overrides[hdr.trim().toLowerCase()] = field;
    }
    if (f.mode === "provided" && Object.keys(overrides).length)
      cfg.provided_column_overrides = overrides;
    if (f.mode === "provided" && f.limit > 0) cfg.process_limit = f.limit;
    // Research providers: declare the selected catalog entries, pick the primary,
    // and enable the ensemble when >1 is chosen.
    const chosen = f.providers
      .map((n) => provCatalog.find((p) => p.name === n))
      .filter(Boolean);
    if (chosen.length) {
      cfg.llm_providers = chosen.map((p) => ({
        name: p.name,
        type: p.type,
        web_search: p.web_search,
        ...(p.model ? { model: p.model } : {}),
        ...(p.api_key_env ? { api_key_env: p.api_key_env } : {}),
        ...(p.endpoint_env ? { endpoint_env: p.endpoint_env } : {}),
        ...(p.assistant_id_env ? { assistant_id_env: p.assistant_id_env } : {}),
      }));
      const primary = chosen.find((p) => p.is_default_research) || chosen[0];
      cfg.research_provider = primary.name;
      if (chosen.length > 1) cfg.research_providers = chosen.map((p) => p.name);
    }
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
      if (campaignId) await api.updateCampaign(campaignId, f.name, buildConfig());
      else await api.createCampaign(f.name, buildConfig());
      onCreated();
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  async function regeneratePrompt(slug) {
    setPromptLoading(true);
    setPromptErr("");
    try {
      const perVertical = f.mode === "discover" && f.verticals.length > 0;
      const want = slug !== undefined ? slug : previewVertical;
      const r = await api.previewPrompt(buildConfig(), perVertical ? want || undefined : undefined);
      setF((prev) => ({ ...prev, search_prompt: r.prompt }));
      if (perVertical && r.vertical) setPreviewVertical(r.vertical);
    } catch (e) {
      setPromptErr(String(e.message || e));
    } finally {
      setPromptLoading(false);
    }
  }

  const onPreviewVertical = (e) => {
    const slug = e.target.value;
    setPreviewVertical(slug);
    regeneratePrompt(slug);
  };

  // Load the enabled research-provider catalog once; default-select the primary
  // provider when the campaign hasn't chosen any yet.
  useEffect(() => {
    (async () => {
      try {
        const data = await api.listProviders();
        const enabled = (data.results || data).filter((p) => p.enabled);
        setProvCatalog(enabled);
        setF((prev) => {
          if (prev.providers.length) return prev;
          const def = enabled.find((p) => p.is_default_research) || enabled[0];
          return def ? { ...prev, providers: [def.name] } : prev;
        });
      } catch {
        /* ignore — providers section just won't render */
      }
    })();
  }, []);

  // Auto-fill the research prompt the first time the user reaches the Prompt step.
  // Seeds the value prop / fit criteria from the vendor preset when still empty.
  useEffect(() => {
    if (STEPS[step] !== "Prompt" || f.search_prompt || promptLoading || promptErr) return;
    (async () => {
      if (f.vendor && !f.value_prop && !f.fit_criteria) {
        try {
          const p = await api.vendorPreset(f.vendor, f.target_type);
          if (p.known) {
            setF((prev) => ({
              ...prev,
              value_prop: prev.value_prop || p.value_prop || "",
              fit_criteria: prev.fit_criteria || (p.fit_criteria || []).join("\n"),
            }));
          }
        } catch {
          /* preset is best-effort; the server also enriches on preview */
        }
      }
      regeneratePrompt();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  // Load the qualification criteria (universal vs vendor-specific) for the cards.
  useEffect(() => {
    if (STEPS[step] !== "Prompt" || !f.vendor) return;
    api.vendorPreset(f.vendor, f.target_type)
      .then((p) => p.known && setDims({
        universal: p.universal_dimensions || [],
        specific: p.specific_dimensions || [],
      }))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, f.vendor, f.target_type]);

  // Live email preview (real vendor template + sample body in the chosen language).
  useEffect(() => {
    if (STEPS[step] !== "Outreach" || !f.outreach_enabled) return;
    setEmailPreview((p) => ({ ...p, loading: true }));
    api.outreachPreview(buildConfig())
      .then((r) => setEmailPreview({ html: r.html || "", source: r.source || "", loading: false }))
      .catch(() => setEmailPreview({ html: "", source: "", loading: false }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, f.vendor, f.outreach_language, f.logo_path]);

  // Load discover verticals (grouped by tier) when the vendor is set in discover
  // mode; default-check Core+Secondary the first time (Defer stays unchecked).
  useEffect(() => {
    if (STEPS[step] !== "Setup" || f.mode !== "discover" || !f.vendor) return;
    api.vendorVerticals(f.vendor)
      .then((r) => {
        if (!r.known) { setVtree({ tiers: { core: [], secondary: [], defer: [] }, exclusion_note: "" }); return; }
        setVtree(r);
        setF((prev) => {
          if (prev.verticals && prev.verticals.length) return prev;
          const def = [...(r.tiers.core || []), ...(r.tiers.secondary || [])].map((v) => v.slug);
          return { ...prev, verticals: def };
        });
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, f.mode, f.vendor]);

  // Load the curated Datech country list (grouped by region) for discover mode.
  useEffect(() => {
    if (STEPS[step] !== "Setup" || f.mode !== "discover" || ctree) return;
    api.datechCountries()
      .then((r) => setCtree(r.regions || {}))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, f.mode]);

  return (
    <div className="card">
      <ol className="steps">
        {STEPS.map((s, i) => (
          <li key={s} className={i === step ? "on" : i < step ? "done" : ""}
              onClick={() => goTo(i)} role="button">{s}</li>
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
            <select value={f.vendor} onChange={onVendor}>
              <option value="">— select vendor —</option>
              {VENDORS.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
          <label>Mode
            <select value={f.mode} onChange={set("mode")}>
              <option value="provided">provided (I have a list)</option>
              <option value="discover">discover (find them)</option>
            </select>
          </label>
          {f.mode === "provided" && (
            <label>Country (fallback)
              <input value={f.country} onChange={set("country")} placeholder="Spain" />
              <small className="hint">Used when a row has no country. Per-row country comes from the uploaded list.</small>
            </label>
          )}
          {f.mode === "discover" && (
            <div className="field">
              <span className="lbl section-h">Markets — one research pass per country per vertical</span>
              {!ctree ? (
                <small className="hint">Loading countries…</small>
              ) : (
                <>
                  {Object.entries(ctree).map(([region, list]) => {
                    const on = list.filter((c) => f.countries.includes(c)).length;
                    return (
                      <div key={region} className="vtier">
                        <h4 className="vtier-h">
                          {region} <span className="hint">{on}/{list.length}</span>
                          <button type="button" className="link region-pick" onClick={() => toggleRegion(list)}>
                            {list.every((c) => f.countries.includes(c)) ? "clear" : "all"}
                          </button>
                        </h4>
                        <div className="vgrid">
                          {list.map((c) => (
                            <label key={c} className="vchk">
                              <input
                                type="checkbox"
                                checked={f.countries.includes(c)}
                                onChange={() => toggleCountry(c)}
                              />
                              <span>{c}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                  <small className="hint">{f.countries.length} country(ies) selected.</small>
                </>
              )}
            </div>
          )}
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
                    {remapping ? " · re-analyzing…" : ""}
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
          {f.mode === "provided" && listReport && (
            <label>How many to process
              <select value={f.limitSel} onChange={onLimitSel}>
                <option value="all">All ({listReport.with_company})</option>
                <option value="20">First 20</option>
                <option value="50">First 50</option>
                <option value="100">First 100</option>
                <option value="custom">Custom…</option>
              </select>
              {f.limitSel === "custom" && (
                <input type="number" min="1" value={f.limit} onChange={setNum("limit")} />
              )}
            </label>
          )}
          {f.mode === "discover" && f.vendor && (
            <div className="field">
              <span className="lbl section-h">Reseller verticals to recruit from</span>
              {!vtree ? (
                <small className="hint">Loading verticals…</small>
              ) : (
                <>
                  {["core", "secondary", "defer"].map((tier) => {
                    const items = (vtree.tiers && vtree.tiers[tier]) || [];
                    if (!items.length) return null;
                    const label =
                      tier === "core" ? "Core" : tier === "secondary" ? "Secondary" : "Defer (off by default)";
                    return (
                      <div key={tier} className="vtier">
                        <h4 className="vtier-h">{label} <span className="hint">{items.length}</span></h4>
                        <div className="vgrid">
                          {items.map((v) => (
                            <label key={v.slug} className="vchk" title={v.focus}>
                              <input
                                type="checkbox"
                                checked={f.verticals.includes(v.slug)}
                                onChange={() => toggleVertical(v.slug)}
                              />
                              <span>{v.name}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                  {vtree.exclusion_note && <div className="estimate warn">⛔ {vtree.exclusion_note}</div>}
                  <small className="hint">
                    {f.verticals.length} vertical(s) selected · one research pass per vertical.
                  </small>
                </>
              )}
            </div>
          )}
        </section>
      )}

      {STEPS[step] === "Prompt" && (
        <section className="grid">
          <h2>Research prompt</h2>
          <ul className="summary">
            <li>Researches each company and scores fit as a <b>{f.vendor || "vendor"}</b> {f.target_type === "resellers" ? "reseller" : "account"} in <b>{f.mode === "provided" && f.colMap.country ? "each row’s country" : (f.country || "—")}</b>.</li>
            <li>Requires a source URL for every claim — without evidence a company can’t exceed the capped tier.</li>
            <li>Edit the prompt directly, or tweak the value prop / fit criteria below and regenerate.</li>
          </ul>
          {provCatalog.length > 0 && (
            <div className="field">
              <span className="lbl">Research models</span>
              <div className="checks">
                {provCatalog.map((p) => (
                  <label className="chk" key={p.name}>
                    <input
                      type="checkbox"
                      checked={f.providers.includes(p.name)}
                      onChange={() => toggleProvider(p.name)}
                    />
                    <span>{p.label || p.name}{p.web_search ? "" : " (no web search)"}</span>
                  </label>
                ))}
              </div>
              <small className="hint">
                {f.providers.length > 1
                  ? `Ensemble: ${f.providers.length} models run research; scores are averaged and companies found by several models get a confidence boost.`
                  : "Pick one model, or select several to run an ensemble. Manage the catalog in Settings."}
              </small>
            </div>
          )}
          {(dims.universal.length > 0 || dims.specific.length > 0) && (
            <div className="criteria">
              <div className="crit-group">
                <h4>Universal criteria <span className="hint">(any vendor · 60 pts)</span></h4>
                <div className="cards">
                  {dims.universal.map((d) => (
                    <div className="crit-card" key={d.name}>
                      <div className="crit-top"><b>{d.name}</b><span>{d.max_points} pts</span></div>
                      <small>{d.description}</small>
                    </div>
                  ))}
                </div>
              </div>
              <div className="crit-group">
                <h4>{f.vendor || "Vendor"}-specific criteria <span className="hint">(40 pts)</span></h4>
                <div className="cards">
                  {dims.specific.map((d) => (
                    <div className="crit-card spec" key={d.name}>
                      <div className="crit-top"><b>{d.name}</b><span>{d.max_points} pts</span></div>
                      <small>{d.description}</small>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
          {f.mode === "discover" && f.verticals.length > 0 && vtree && (() => {
            const all = [
              ...(vtree.tiers.core || []),
              ...(vtree.tiers.secondary || []),
              ...(vtree.tiers.defer || []),
            ];
            const opts = all.filter((v) => f.verticals.includes(v.slug));
            return (
              <label>Preview vertical prompt
                <select value={previewVertical || (opts[0] && opts[0].slug) || ""} onChange={onPreviewVertical}>
                  {opts.map((v) => <option key={v.slug} value={v.slug}>{v.name}</option>)}
                </select>
                <small className="hint">
                  Each selected vertical is researched with its OWN prompt (its own vendor landscape) —
                  {opts.length} in total. This is a read-only preview.
                </small>
              </label>
            );
          })()}
          {promptLoading ? (
            <div className="estimate">Building prompt…</div>
          ) : (
            <textarea
              className="prompt-area"
              value={f.search_prompt}
              onChange={set("search_prompt")}
              rows={16}
              spellCheck={false}
              readOnly={f.mode === "discover" && f.verticals.length > 0}
            />
          )}
          {promptErr && <p className="error">{promptErr}</p>}
          {!(f.mode === "discover" && f.verticals.length > 0) && (
            <div>
              <button type="button" className="link" onClick={() => regeneratePrompt()} disabled={promptLoading}>
                ↻ Regenerate prompt from fields (discards edits)
              </button>
            </div>
          )}
          <details>
            <summary className="link">Advanced: value proposition & fit criteria</summary>
            <div className="grid" style={{ marginTop: 8 }}>
              <label>Value proposition<textarea value={f.value_prop} onChange={set("value_prop")} rows={3} placeholder="Why this vendor fits this audience…" /></label>
              <label>Fit criteria (one per line)<textarea value={f.fit_criteria} onChange={set("fit_criteria")} rows={4} placeholder={"Sells CAD/design software\nActive construction projects"} /></label>
            </div>
          </details>
          {f.mode === "provided" && <small className="hint">The [[COMPANIES]] marker is replaced with your uploaded list at run time.</small>}
        </section>
      )}

      {STEPS[step] === "Enrich" && (
        <section className="grid">
          <h2>Enrichment</h2>
          <div className="field">
            <span className="lbl">What to find</span>
            <div className="checks">
              <label className="chk">
                <input type="checkbox" checked={wantEmail} onChange={toggleEmail} /> Emails
              </label>
              <label className="chk">
                <input type="checkbox" checked={wantPhone} disabled={!wantEmail} onChange={togglePhone} /> Phones
              </label>
            </div>
            <small className="hint">Phones require the contact’s email first. Uncheck both to qualify only.</small>
          </div>
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
          {f.want === "none" ? (
            <div className="estimate">No enrichment (qualify only).</div>
          ) : f.provider !== "apollo" ? (
            <div className="estimate">LARA web search — no Apollo credits.</div>
          ) : (
            <div className="estimate">
              ≈ <b>{perCompany}</b> credits/company (1 × {f.max_contacts} email{f.max_contacts > 1 ? "s" : ""}{f.want === "emails+phones" ? ` + 8 × ${f.max_contacts} phone${f.max_contacts > 1 ? "s" : ""}` : ""})
              {effectiveCount > 0 ? (
                <> · <b>≈ {totalCredits.toLocaleString()}</b> credits total for {effectiveCount.toLocaleString()} compan{effectiveCount === 1 ? "y" : "ies"}{f.limit > 0 ? " (limited)" : ""}</>
              ) : (
                <> · upload a list in Setup to estimate the total</>
              )}
            </div>
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
              <label>Email language
                <select value={f.outreach_language} onChange={set("outreach_language")}>
                  <option value="">Auto (match each company's country)</option>
                  <option value="en">English</option>
                  <option value="es">Español</option>
                  <option value="pt">Português</option>
                </select>
                <small className="hint">Auto uses each company's country; pick one to force it for all drafts.</small>
              </label>
              <div className="field">
                <span className="lbl">Custom header / logo (optional)</span>
                <input type="file" accept=".png,.jpg,.jpeg,.gif,.webp" onChange={onLogoUpload} />
                <small className="hint">By default each vendor uses its own branded template. Upload here to override with your own header/banner.</small>
                {f.logo_path && <small className="hint">Custom header set: {f.logo_path.split(/[\\/]/).pop()}</small>}
              </div>
              <div className="field">
                <span className="lbl">Email preview{emailPreview.source ? ` (${emailPreview.source})` : ""}</span>
                {emailPreview.loading ? (
                  <div className="estimate">Rendering preview…</div>
                ) : emailPreview.html ? (
                  <iframe className="mailpreview" title="email preview" srcDoc={emailPreview.html} />
                ) : (
                  <small className="hint">Preview unavailable — complete the earlier steps.</small>
                )}
              </div>
            </>
          )}
        </section>
      )}

      {STEPS[step] === "Review" && (
        <section>
          <h2>Review</h2>
          <ul className="summary">
            <li>Targeting <b>{f.target_type}</b>{f.vendor ? <> for <b>{f.vendor}</b></> : null} in <b>{f.mode === "provided" && f.colMap.country ? "per-row country" : (f.country || "—")}</b>{f.mode === "provided" && f.colMap.country && f.country ? <> (fallback {f.country})</> : null}.</li>
            <li>Input: <b>{f.mode === "provided" ? "uploaded list" : "discover (find them)"}</b>{f.mode === "provided" && listReport ? <> — {effectiveCount.toLocaleString()} of {listReport.with_company.toLocaleString()} companies{f.limit > 0 ? " (limited)" : ""}</> : null}.</li>
            <li>
              Enrichment:{" "}
              {f.want === "none" ? (
                <b>none (qualify only)</b>
              ) : (
                <>
                  <b>{f.provider === "apollo" ? "Apollo" : "LARA web search"}</b> — up to <b>{f.max_contacts}</b> contacts ({f.want})
                  {f.provider === "apollo" ? <> ≈ <b>{perCompany}</b>/company{effectiveCount > 0 ? <>, <b>≈ {totalCredits.toLocaleString()}</b> total</> : null}</> : null}
                </>
              )}.
            </li>
            <li>
              Outreach:{" "}
              {f.outreach_enabled ? (
                <>.eml drafts for tiers <b>{[...f.tiers].sort().join(", ") || "—"}</b>{f.sender_name || f.sender_email ? <> — from <b>{f.sender_name || "—"}</b> ({f.sender_email || "—"})</> : null}</>
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
            {busy ? "Saving…" : campaignId ? "Save changes" : "Create campaign"}
          </button>
        )}
      </footer>
    </div>
  );
}

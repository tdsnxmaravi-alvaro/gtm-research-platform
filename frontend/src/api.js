// Thin API client for the Django/DRF backend.
const BASE = "/api";

async function req(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail;
    try { detail = await res.json(); } catch { detail = await res.text(); }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  listCampaigns: () => req("/campaigns/"),
  createCampaign: (name, config) =>
    req("/campaigns/", { method: "POST", body: JSON.stringify({ name, config }) }),
  updateCampaign: (id, name, config) =>
    req(`/campaigns/${id}/`, { method: "PUT", body: JSON.stringify({ name, config }) }),
  deleteCampaign: (id) => req(`/campaigns/${id}/`, { method: "DELETE" }),
  previewPrompt: (config, vertical) =>
    req("/campaigns/preview_prompt/", {
      method: "POST",
      body: JSON.stringify(vertical ? { config, vertical } : { config }),
    }),
  vendorPreset: (vendor, targetType) =>
    req(`/campaigns/vendor_preset/?vendor=${encodeURIComponent(vendor)}&target_type=${encodeURIComponent(targetType)}`),
  vendorVerticals: (vendor) =>
    req(`/campaigns/vendor_verticals/?vendor=${encodeURIComponent(vendor)}`),
  datechCountries: () => req("/campaigns/datech_countries/"),
  outreachPreview: (config, { signal } = {}) =>
    req("/campaigns/outreach_preview/", {
      method: "POST",
      body: JSON.stringify({ config }),
      signal,
    }),
  remapList: (path, mapping, { signal } = {}) =>
    req("/campaigns/remap_list/", {
      method: "POST",
      body: JSON.stringify({ path, mapping }),
      signal,
    }),
  uploadList: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(BASE + "/campaigns/upload_list/", { method: "POST", body: fd }).then(
      async (res) => {
        if (!res.ok) {
          let d;
          try { d = await res.json(); } catch { d = await res.text(); }
          throw new Error(typeof d === "string" ? d : d.error || JSON.stringify(d));
        }
        return res.json();
      }
    );
  },
  uploadLogo: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(BASE + "/campaigns/upload_logo/", { method: "POST", body: fd }).then(
      async (res) => {
        if (!res.ok) {
          let d;
          try { d = await res.json(); } catch { d = await res.text(); }
          throw new Error(typeof d === "string" ? d : d.error || JSON.stringify(d));
        }
        return res.json();
      }
    );
  },
  runStage: (id, stage) => req(`/campaigns/${id}/${stage}/`, { method: "POST" }),
  start: (id) => req(`/campaigns/${id}/start/`, { method: "POST" }),
  stop: (id) => req(`/campaigns/${id}/stop/`, { method: "POST" }),
  pause: (id) => req(`/campaigns/${id}/pause/`, { method: "POST" }),
  relaunch: (id) => req(`/campaigns/${id}/relaunch/`, { method: "POST" }),
  relaunchSummary: (id) => req(`/campaigns/${id}/relaunch_summary/`),
  campaignStatus: (id) => req(`/campaigns/${id}/status/`),
  campaignRuns: (id) => req(`/campaigns/${id}/runs/`),
  results: (id) => req(`/campaigns/${id}/results/`),
  getRun: (id) => req(`/runs/${id}/`),
  listProviders: () => req("/providers/"),
  updateProvider: (id, patch) =>
    req(`/providers/${id}/`, { method: "PATCH", body: JSON.stringify(patch) }),
  createProvider: (body) =>
    req("/providers/", { method: "POST", body: JSON.stringify(body) }),
  deleteProvider: (id) => req(`/providers/${id}/`, { method: "DELETE" }),
  apolloCredits: () => req("/campaigns/apollo_credits/"),
};

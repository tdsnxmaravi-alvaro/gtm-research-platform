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
  previewPrompt: (config) =>
    req("/campaigns/preview_prompt/", { method: "POST", body: JSON.stringify({ config }) }),
  vendorPreset: (vendor, targetType) =>
    req(`/campaigns/vendor_preset/?vendor=${encodeURIComponent(vendor)}&target_type=${encodeURIComponent(targetType)}`),
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
  campaignStatus: (id) => req(`/campaigns/${id}/status/`),
  results: (id) => req(`/campaigns/${id}/results/`),
  getRun: (id) => req(`/runs/${id}/`),
};

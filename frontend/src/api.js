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
  runStage: (id, stage) => req(`/campaigns/${id}/${stage}/`, { method: "POST" }),
  results: (id) => req(`/campaigns/${id}/results/`),
  getRun: (id) => req(`/runs/${id}/`),
};

import React, { useState, useEffect } from "react";
import Wizard from "./Wizard.jsx";
import Campaigns from "./Campaigns.jsx";
import Settings from "./Settings.jsx";
import { api } from "./api.js";
import logoWhite from "./assets/datech-logo-white.png";

export default function App() {
  const [tab, setTab] = useState("new");
  const [editing, setEditing] = useState(null); // campaign being edited, or null
  const [credits, setCredits] = useState(null); // Apollo credit capacity (header badge)

  // Refresh the Apollo credit badge on load and tab change, then hourly.
  useEffect(() => {
    let alive = true;
    const load = () => api.apolloCredits().then((c) => alive && setCredits(c)).catch(() => {});
    load();
    const t = setInterval(load, 3600000);
    return () => { alive = false; clearInterval(t); };
  }, [tab]);

  const newCampaign = () => {
    setEditing(null);
    setTab("new");
  };

  return (
    <div className="app">
      <header>
        <div className="brand">
          <img className="brand-logo" src={logoWhite} alt="TD SYNNEX Datech" />
          <span className="brand-divider" aria-hidden="true" />
          <h1>GTM <span className="accent">Research Platform</span></h1>
        </div>
        {credits && credits.configured && credits.remaining != null && (
          <span className="credits-badge"
                title={`Apollo shared credits — ~${credits.emails?.toLocaleString()} emails or ~${credits.phones?.toLocaleString()} phone reveals`}>
            <b>{credits.remaining.toLocaleString()}</b> Apollo credits
          </span>
        )}
        <nav>
          <button className={tab === "new" ? "on" : ""} onClick={newCampaign}>
            {editing ? "Edit campaign" : "New campaign"}
          </button>
          <button className={tab === "list" ? "on" : ""} onClick={() => setTab("list")}>
            Campaigns
          </button>
          <button className={tab === "settings" ? "on" : ""} onClick={() => setTab("settings")}>
            Settings
          </button>
        </nav>
      </header>
      <main>
        {tab === "new" ? (
          <Wizard
            key={editing ? editing.id : "new"}
            initialConfig={editing ? editing.config : null}
            campaignId={editing ? editing.id : null}
            onCreated={() => {
              setEditing(null);
              setTab("list");
            }}
          />
        ) : tab === "settings" ? (
          <Settings />
        ) : (
          <Campaigns
            onEdit={(c) => {
              setEditing(c);
              setTab("new");
            }}
          />
        )}
      </main>
    </div>
  );
}

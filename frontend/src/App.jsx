import React, { useState } from "react";
import Wizard from "./Wizard.jsx";
import Campaigns from "./Campaigns.jsx";
import logoWhite from "./assets/datech-logo-white.png";

export default function App() {
  const [tab, setTab] = useState("new");
  const [editing, setEditing] = useState(null); // campaign being edited, or null

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
        <nav>
          <button className={tab === "new" ? "on" : ""} onClick={newCampaign}>
            {editing ? "Edit campaign" : "New campaign"}
          </button>
          <button className={tab === "list" ? "on" : ""} onClick={() => setTab("list")}>
            Campaigns
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

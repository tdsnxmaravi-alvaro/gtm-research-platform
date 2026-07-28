import React, { useState } from "react";
import Wizard from "./Wizard.jsx";
import Campaigns from "./Campaigns.jsx";

export default function App() {
  const [tab, setTab] = useState("new");
  return (
    <div className="app">
      <header>
        <h1>GTM Research Platform</h1>
        <nav>
          <button className={tab === "new" ? "on" : ""} onClick={() => setTab("new")}>
            New campaign
          </button>
          <button className={tab === "list" ? "on" : ""} onClick={() => setTab("list")}>
            Campaigns
          </button>
        </nav>
      </header>
      <main>{tab === "new" ? <Wizard onCreated={() => setTab("list")} /> : <Campaigns />}</main>
    </div>
  );
}

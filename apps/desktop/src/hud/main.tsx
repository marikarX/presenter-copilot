import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { HudApp } from "./HudApp";
import "./hud.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <HudApp />
  </StrictMode>,
);

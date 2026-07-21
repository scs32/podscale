import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/tailarr.css";
import "./styles/themes.css";
import { App } from "./App";
import { initTheme } from "./lib/theme";

initTheme(); // stored theme paints before first render

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

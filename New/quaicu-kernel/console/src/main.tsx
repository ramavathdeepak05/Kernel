import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
// Self-hosted fonts (sovereignty: no Google CDN call → no client-IP leak to a third party). Vite
// bundles the woff2 into dist/assets and rewrites the @font-face URLs to same-origin. Variable builds
// cover every weight the design system uses (Inter 400–700, Space Grotesk 500–700, JetBrains 400–600).
import "@fontsource-variable/inter";
import "@fontsource-variable/space-grotesk";
import "@fontsource-variable/jetbrains-mono";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter basename="/app">
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);

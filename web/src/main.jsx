import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "../../ekran-react/src/App.tsx";
import "../../ekran-react/src/index.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
import { Shell } from "./components/Shell";
import { Dashboard } from "./pages/Dashboard";

// Phase 2 delivers the shell + dashboard as a working vertical slice against
// the live JSON API. Catalog install, custom-pod, and shares screens follow
// in Phase 3 (the sidebar links are placeholders until then).
export function App() {
  return (
    <Shell active="dashboard">
      <Dashboard />
    </Shell>
  );
}

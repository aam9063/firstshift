import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./features/shell/AppShell";
import { CandidateJourneyPage } from "./features/journey/CandidateJourneyPage";
import { CandidatesPage } from "./features/candidates/CandidatesPage";
import { LiveActivityPage } from "./features/live/LiveActivityPage";
import { OverviewPage } from "./features/overview/OverviewPage";
import { RestaurantDetailPage } from "./features/restaurants/RestaurantDetailPage";
import { RestaurantsPage } from "./features/restaurants/RestaurantsPage";
import { OpsPage } from "./features/ops/OpsPage";
import { EvalsPage } from "./features/evals/EvalsPage";
import { CompliancePage } from "./features/compliance/CompliancePage";
import { SimulatorPage } from "./features/simulator/SimulatorPage";
import { HealthStatus } from "./components/HealthStatus";

const queryClient = new QueryClient();

/* The compliance spec view (specs/04b-console.md section 3.8) is the only
   route without its own page component left; it renders the health check as a
   placeholder until a dedicated feature lands. */
function PlaceholderPage({ title }: { title: string }) {
  return (
    <div>
      <p className="text-micro font-semibold uppercase tracking-wide text-steel">
        FirstShift console
      </p>
      <h1 className="mt-1 text-heading-3 font-semibold text-ink">{title}</h1>
      <p className="mt-2 max-w-xl text-body-sm text-steel">
        This view is not part of the console UI feature yet. It is described in
        specs/04b-console.md and will land in a later feature.
      </p>
      <div className="mt-6 max-w-sm">
        <HealthStatus />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<AppShell><OverviewPage /></AppShell>} />
          <Route path="/live" element={<AppShell><LiveActivityPage /></AppShell>} />
          <Route
            path="/candidates"
            element={<AppShell><CandidatesPage /></AppShell>}
          />
          <Route
            path="/candidates/:id"
            element={<AppShell><CandidateJourneyPage /></AppShell>}
          />
          <Route
            path="/restaurants"
            element={<AppShell><RestaurantsPage /></AppShell>}
          />
          <Route
            path="/restaurants/:id"
            element={<AppShell><RestaurantDetailPage /></AppShell>}
          />
          <Route path="/ops" element={<AppShell><OpsPage /></AppShell>} />
          <Route path="/evals" element={<AppShell><EvalsPage /></AppShell>} />
          <Route path="/compliance" element={<AppShell><CompliancePage /></AppShell>} />
          <Route path="/simulator" element={<AppShell><SimulatorPage /></AppShell>} />
          <Route
            path="*"
            element={<AppShell><PlaceholderPage title="Not found" /></AppShell>}
          />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

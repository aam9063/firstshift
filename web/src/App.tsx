import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./features/shell/AppShell";
import { CandidateJourneyPage } from "./features/journey/CandidateJourneyPage";
import { LiveActivityPage } from "./features/live/LiveActivityPage";
import { OverviewPage } from "./features/overview/OverviewPage";
import { HealthStatus } from "./components/HealthStatus";

const queryClient = new QueryClient();

/* Views outside the three mockups are placeholders in this feature
   (odd/tasks/console-ui.md, S3). */
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
            element={<AppShell><PlaceholderPage title="Candidates" /></AppShell>}
          />
          <Route
            path="/candidates/:id"
            element={<AppShell><CandidateJourneyPage /></AppShell>}
          />
          {["/restaurants", "/ops", "/simulator", "/evals", "/compliance"].map(
            (path) => (
              <Route
                key={path}
                path={path}
                element={
                  <AppShell>
                    <PlaceholderPage title={path.replace("/", "").replace(/^\w/, (c) => c.toUpperCase())} />
                  </AppShell>
                }
              />
            ),
          )}
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

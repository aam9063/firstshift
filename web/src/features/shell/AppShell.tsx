import { useState } from "react";
import { overviewFixture } from "../../mocks/fixtures";
import type { ConsoleRole } from "./AppHeader";
import { AppHeader } from "./AppHeader";
import { Sidebar } from "./Sidebar";
import { SimulationBanner } from "./SimulationBanner";

/* App shell per specs/04b-console.md section 4.2: left sidebar, center content.
   The banner reads the simulation context from the mock dataset until the
   backend session exposes it through the API. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [role, setRole] = useState<ConsoleRole>("Talent team");

  return (
    <div className="flex min-h-screen flex-col">
      <SimulationBanner
        simClock={overviewFixture.simClock}
        pilotDay={overviewFixture.pilotDay}
        pilotDaysTotal={overviewFixture.pilotDaysTotal}
      />
      <AppHeader role={role} onRoleChange={setRole} />
      <div className="flex flex-1">
        <Sidebar />
        <main className="min-w-0 flex-1 bg-canvas px-8 py-6">{children}</main>
      </div>
    </div>
  );
}

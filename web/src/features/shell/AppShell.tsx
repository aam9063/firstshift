import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchOverview } from "../../api/client";
import type { ConsoleRole } from "./AppHeader";
import { AppHeader } from "./AppHeader";
import { Sidebar } from "./Sidebar";
import { SimulationBanner } from "./SimulationBanner";

/* App shell per specs/04b-console.md section 4.2: left sidebar, center
   content. The banner reads the simulation context from GET /api/overview.
   Responsive per web/DESIGN.md "Responsive Behavior": below 1024px the
   sidebar becomes a drawer with a 44px toggle in the header. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [role, setRole] = useState<ConsoleRole>("Talent team");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { data: overview } = useQuery({ queryKey: ["overview"], queryFn: fetchOverview });

  return (
    <div className="flex min-h-screen flex-col">
      <SimulationBanner
        simClock={overview?.simClock ?? ""}
        pilotDay={overview?.pilotDay ?? 0}
        pilotDaysTotal={overview?.pilotDaysTotal ?? 0}
      />
      <AppHeader role={role} onRoleChange={setRole} onMenuClick={() => setDrawerOpen(true)} />
      <div className="flex flex-1">
        <Sidebar open={drawerOpen} onClose={() => setDrawerOpen(false)} />
        <main className="min-w-0 flex-1 bg-canvas px-4 py-6 sm:px-8">{children}</main>
      </div>
    </div>
  );
}

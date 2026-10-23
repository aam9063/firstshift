import { NavLink } from "react-router-dom";

interface NavItem {
  to: string;
  label: string;
  icon: "overview" | "pulse" | "people" | "store" | "alert" | "sim" | "chart" | "shield";
  badge?: string;
  live?: boolean;
}

interface NavSection {
  heading: string;
  items: NavItem[];
}

/* Navigation matches specs/04b-console.md section 3. Below 1024px it renders
   as a drawer (odd/tasks/console-live.md T4); onClose runs on navigation so
   the drawer closes after choosing a view. */
const SECTIONS: NavSection[] = [
  {
    heading: "Workspace",
    items: [
      { to: "/", label: "Overview", icon: "overview" },
      { to: "/live", label: "Live activity", icon: "pulse", live: true },
      { to: "/candidates", label: "Candidates", icon: "people" },
      { to: "/restaurants", label: "Restaurants", icon: "store", badge: "15" },
    ],
  },
  {
    heading: "Operations",
    items: [
      { to: "/ops", label: "Escalations", icon: "alert", badge: "5" },
      { to: "/simulator", label: "Simulator", icon: "sim" },
    ],
  },
  {
    heading: "Quality",
    items: [
      { to: "/evals", label: "Evals", icon: "chart", badge: "v3" },
      { to: "/compliance", label: "Compliance", icon: "shield" },
    ],
  },
];

const AGENTS = [
  { id: "recruit", label: "Recruit", version: "recruit@v7" },
  { id: "onboard", label: "Onboard", version: "onboard@v4" },
  { id: "pulse", label: "Pulse", version: "pulse@v2" },
];

function NavIcon({ icon }: { icon: NavItem["icon"] }) {
  const paths: Record<NavItem["icon"], string> = {
    overview: "M2 8h5V2H2v6Zm7 6h5V8H9v6ZM2 14h5v-4H2v4Zm7-8h5V2H9v4Z",
    pulse: "M1 8h3l2-5 3 10 2-5h4",
    people: "M5.5 7a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Zm6 1a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM1 13c0-2.2 2-4 4.5-4S10 10.8 10 13m1-3.5c1.9.2 4 1.5 4 3.5",
    store: "M2 6l1-3h10l1 3M2 6v8h12V6M2 6h12M6 14v-4h4v4",
    alert: "M8 2 1.5 13h13L8 2Zm0 4v3.5m0 1.8v.2",
    sim: "M3 5h10v6H3V5Zm2 8h6M5 8h.01M8 8h.01M11 8h.01",
    chart: "M2 14V8m4 6V4m4 10v-4m4 4V6",
    shield: "M8 1.5 2.5 3.5v4c0 3.5 2.3 6 5.5 7 3.2-1 5.5-3.5 5.5-7v-4L8 1.5Z",
  };
  return (
    <svg aria-hidden viewBox="0 0 16 16" className="h-4 w-4 shrink-0">
      <path
        d={paths[icon]}
        fill={icon === "overview" ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <>
      {/* Backdrop closes the drawer below 1024px (DESIGN.md collapsing strategy) */}
      {open && (
        <button
          type="button"
          aria-label="Close navigation"
          onClick={onClose}
          className="fixed inset-0 z-30 bg-ink/40 lg:hidden"
        />
      )}
      <nav
        aria-label="Console"
        className={`fixed inset-y-0 left-0 z-40 flex w-64 shrink-0 transform flex-col gap-6 overflow-y-auto border-r border-hairline-soft bg-canvas px-3 pb-5 pt-14 transition-transform duration-150 lg:static lg:z-auto lg:w-60 lg:translate-x-0 lg:pt-5 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
      {SECTIONS.map((section) => (
        <div key={section.heading}>
          <p className="px-3 pb-1 text-micro font-semibold uppercase tracking-wide text-steel">
            {section.heading}
          </p>
          <ul>
            {section.items.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === "/"}
                  onClick={onClose}
                  className={({ isActive }) =>
                    `flex h-11 items-center gap-2.5 rounded-sm px-3 text-body-sm lg:h-8 ${
                      isActive
                        ? "bg-surface font-medium text-ink"
                        : "text-steel hover:bg-surface hover:text-ink"
                    }`
                  }
                >
                  <NavIcon icon={item.icon} />
                  <span>{item.label}</span>
                  <span className="ml-auto flex items-center gap-1.5">
                    {item.live && (
                      <span className="inline-block h-1.5 w-1.5 rounded-full bg-brand-green" aria-label="live" />
                    )}
                    {item.badge && (
                      <span className="text-micro text-stone">{item.badge}</span>
                    )}
                  </span>
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}

      <div className="rounded-lg border border-hairline-soft bg-canvas p-3">
        <p className="px-1 pb-2 text-micro font-semibold uppercase tracking-wide text-steel">
          Agents
        </p>
        <ul className="flex flex-col gap-2 px-1">
          {AGENTS.map((agent) => (
            <li key={agent.id} className="flex items-center gap-2 text-body-sm">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-brand-green" aria-label="running" />
              <span className="text-ink">{agent.label}</span>
              <span className="ml-auto font-mono text-micro text-steel">{agent.version}</span>
            </li>
          ))}
        </ul>
        <button
          type="button"
          className="mt-3 flex h-11 w-full items-center justify-center rounded-full border border-hairline text-body-sm-medium text-ink lg:h-8"
        >
          Pause all agents
        </button>
      </div>
    </nav>
    </>
  );
}

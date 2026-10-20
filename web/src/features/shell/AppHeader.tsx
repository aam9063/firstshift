import { useState } from "react";

export type ConsoleRole = "Talent team" | "DPO" | "Ops";

const ROLES: ConsoleRole[] = ["Talent team", "DPO", "Ops"];

/* In the prototype a role picker simulates the logged-in user
   (specs/04b-console.md section 2); real SSO and RBAC are a later phase. */
export function AppHeader({ role, onRoleChange }: {
  role: ConsoleRole;
  onRoleChange: (role: ConsoleRole) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <header className="flex h-14 items-center justify-between border-b border-hairline-soft bg-canvas px-4">
      <div className="flex items-center gap-4">
        <a href="/" className="flex items-center gap-2 text-body-md font-semibold text-ink">
          FirstShift
        </a>
        <span className="rounded-sm bg-surface px-1.5 py-0.5 text-micro font-medium text-steel">
          HQ
        </span>
        <label className="flex h-9 w-80 items-center gap-2 rounded-md border border-hairline bg-surface px-3">
          <svg aria-hidden viewBox="0 0 16 16" className="h-4 w-4 text-steel">
            <circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
            <path d="m10.5 10.5 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <input
            type="text"
            placeholder="Search candidates, restaurants, events"
            className="w-full bg-transparent text-body-sm text-ink outline-none placeholder:text-steel"
          />
        </label>
      </div>
      <div className="flex items-center gap-3">
        <div className="relative">
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            className="flex h-9 items-center gap-2 rounded-full border border-hairline px-3 text-body-sm-medium text-ink"
          >
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-tag text-on-dark text-micro font-semibold">
              AL
            </span>
            Viewing as {role}
          </button>
          {open && (
            <div className="absolute right-0 top-11 z-10 w-44 rounded-lg border border-hairline bg-canvas p-1 shadow-card">
              {ROLES.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => {
                    onRoleChange(option);
                    setOpen(false);
                  }}
                  className={`w-full rounded-sm px-3 py-2 text-left text-body-sm ${
                    option === role ? "bg-surface text-ink font-medium" : "text-steel"
                  }`}
                >
                  {option}
                </button>
              ))}
            </div>
          )}
        </div>
        <button
          type="button"
          className="flex h-9 items-center rounded-full bg-primary px-5 text-body-sm-medium text-on-primary"
        >
          Open simulator
        </button>
      </div>
    </header>
  );
}

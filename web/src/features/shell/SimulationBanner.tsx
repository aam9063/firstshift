export function SimulationBanner({ simClock, pilotDay, pilotDaysTotal }: {
  simClock: string;
  pilotDay: number;
  pilotDaysTotal: number;
}) {
  return (
    <div className="flex h-9 items-center justify-between bg-canvas-dark px-4 text-xs text-on-dark">
      <div className="flex items-center gap-3">
        <span className="rounded-full bg-on-dark px-2 py-0.5 text-micro font-semibold tracking-wide text-ink">
          SIMULATION
        </span>
        <span className="font-medium">
          Lumbre Burger Group - Costa Blanca pilot - Day {pilotDay} of{" "}
          {pilotDaysTotal}
        </span>
        <span className="text-on-dark-muted">
          All candidates, restaurants and numbers are synthetic
        </span>
      </div>
      <div className="flex items-center gap-2 text-on-dark-muted">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-brand-green" />
        <span className="text-on-dark">sim clock</span>
        <span>{simClock}</span>
      </div>
    </div>
  );
}

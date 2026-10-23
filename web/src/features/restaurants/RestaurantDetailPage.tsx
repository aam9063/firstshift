import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ApiError, fetchRestaurantShifts } from "../../api/client";
import type { RestaurantRow, ShiftRow } from "../../api/types";

/* Restaurant detail (specs/04b-console.md section 3.5, odd/tasks/console-views.md
   T1/S1): the open shifts list grouped by day, which candidate is matched to
   which shift, and the bench. Backend gap: the API exposes the bench as a
   count on GET /api/restaurants only, with no bench list endpoint, so the
   bench section renders the count and an honest empty state. */

function dayLabel(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-GB", {
    weekday: "long",
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  });
}

function ShiftRowView({ shift }: { shift: ShiftRow }) {
  return (
    <li className="flex flex-col gap-1 border-b border-hairline-soft py-2.5 last:border-b-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="text-body-sm text-ink">{shift.label}</p>
        <p className="font-mono text-micro text-stone">
          {shift.role}
          {shift.requiresFoodHygiene ? " · Food hygiene required" : ""}
        </p>
      </div>
      {shift.matchedCandidateName ? (
        <span
          className="inline-flex w-fit items-center gap-1.5 rounded-sm bg-brand-green-soft px-1.5 py-0.5 text-micro font-semibold text-ink"
          title={`Matched from GET /api/restaurants/{id}/shifts - matchedCandidateName`}
        >
          <span aria-hidden className="inline-block h-1.5 w-1.5 rounded-full bg-current" />
          Matched: {shift.matchedCandidateName}
        </span>
      ) : (
        <span
          className="inline-flex w-fit items-center gap-1.5 rounded-sm border border-hairline px-1.5 py-0.5 text-micro font-medium text-charcoal"
          title="GET /api/restaurants/{id}/shifts - no matchedCandidateId yet"
        >
          Unmatched
        </span>
      )}
    </li>
  );
}

function ShiftsByDay({ shifts }: { shifts: ShiftRow[] }) {
  const byDay = new Map<string, ShiftRow[]>();
  for (const shift of shifts) {
    const key = dayLabel(shift.startsAt);
    byDay.set(key, [...(byDay.get(key) ?? []), shift]);
  }
  return (
    <div className="mt-4 space-y-5">
      {[...byDay.entries()].map(([day, dayShifts]) => (
        <section key={day}>
          <h3 className="text-caption font-semibold uppercase tracking-wide text-steel">{day}</h3>
          <ul>
            {dayShifts.map((shift) => (
              <ShiftRowView key={shift.id} shift={shift} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function Header({ restaurant }: { restaurant: RestaurantRow }) {
  return (
    <div>
      <Link
        to="/restaurants"
        className="text-micro font-semibold uppercase tracking-wide text-steel underline-offset-2 hover:underline"
      >
        Restaurants
      </Link>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <h1 className="text-heading-3 font-semibold text-ink">{restaurant.name}</h1>
        <span className="rounded-sm bg-surface px-1.5 py-0.5 font-mono text-micro text-steel">
          {restaurant.cohort}
        </span>
        {restaurant.paused && (
          <span className="rounded-sm bg-brand-warn/15 px-1.5 py-0.5 text-micro font-semibold text-charcoal">
            Paused
          </span>
        )}
      </div>
      <p className="mt-1 font-mono text-micro text-stone">
        {restaurant.code} · {restaurant.city}
      </p>
    </div>
  );
}

export function RestaurantDetailPage() {
  const { id = "" } = useParams();
  const { data, isError, error, isPending } = useQuery({
    queryKey: ["restaurants", id, "shifts"],
    queryFn: () => fetchRestaurantShifts(id),
    enabled: id !== "",
  });

  if (isPending && id !== "") {
    return (
      <p role="status" className="mt-6 text-body-sm text-steel">
        Loading restaurant
      </p>
    );
  }

  if (isError) {
    return (
      <div role="alert" className="mt-6 rounded-lg border border-hairline bg-canvas p-6">
        <p className="text-body-sm-medium text-brand-error">Could not load restaurant</p>
        <p className="mt-1 text-body-sm text-steel">
          {error instanceof ApiError ? error.message : "Unknown error"}
        </p>
      </div>
    );
  }

  if (!data) {
    return <p className="mt-6 text-body-sm text-steel">No restaurant selected</p>;
  }

  const { restaurant, shifts } = data;
  const openShifts = shifts.filter((shift) => shift.status === "open");

  return (
    <div className="min-w-0">
      <Header restaurant={restaurant} />

      <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-[2fr_1fr]">
        <section className="rounded-lg border border-hairline-soft bg-canvas p-4">
          <h2 className="text-heading-5 font-semibold text-ink">Open shifts</h2>
          <p
            className="mt-1 text-caption text-steel"
            title="GET /api/restaurants/{id}/shifts - status open"
          >
            {openShifts.length} open of {restaurant.openShifts} scheduled
          </p>
          <ShiftsByDay shifts={shifts} />
        </section>

        <section className="rounded-lg border border-hairline-soft bg-canvas p-4">
          <h2
            className="text-heading-5 font-semibold text-ink"
            title="GET /api/restaurants - bench count"
          >
            Bench ({restaurant.bench})
          </h2>
          <div className="mt-3 rounded-lg border border-hairline-soft bg-canvas p-6 text-center">
            <p className="text-body-sm-medium text-ink">No benched candidates for this restaurant yet</p>
            <p className="mt-1 text-body-sm text-steel">
              The API exposes the bench as a count only; a bench list endpoint does not exist
              yet, so no names are shown here.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}

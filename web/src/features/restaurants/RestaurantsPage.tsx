import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ApiError, fetchRestaurants } from "../../api/client";
import type { RestaurantRow } from "../../api/types";

/* Restaurants grid (specs/04b-console.md section 3.5, odd/tasks/console-views.md
   T1/S1): one card per restaurant with coverage for the open shifts, bench,
   open candidates and the manager decision median. Every number carries a
   tooltip naming its source endpoint and, for the coverage percentage, the
   formula. Responsive: one column at 390px, two from sm, three from xl. */

function CohortChip({ cohort }: { cohort: RestaurantRow["cohort"] }) {
  return (
    <span className="rounded-sm bg-surface px-1.5 py-0.5 font-mono text-micro text-steel">
      {cohort}
    </span>
  );
}

function RestaurantCard({ restaurant }: { restaurant: RestaurantRow }) {
  const covered = Math.round(restaurant.coveredPct);
  const coverageGap = restaurant.openShifts - Math.round((covered / 100) * restaurant.openShifts);
  return (
    <Link
      to={`/restaurants/${restaurant.id}`}
      className="block rounded-lg border border-hairline-soft bg-canvas p-4 transition-colors hover:bg-surface"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-body-sm-medium text-ink">{restaurant.name}</p>
          <p className="font-mono text-micro text-stone">
            {restaurant.code} · {restaurant.city}
          </p>
        </div>
        <CohortChip cohort={restaurant.cohort} />
      </div>

      {restaurant.paused && (
        <span className="mt-2 inline-block rounded-sm bg-brand-warn/15 px-1.5 py-0.5 text-micro font-semibold text-charcoal">
          Paused
        </span>
      )}

      <dl className="mt-3 space-y-1.5 text-body-sm">
        <div
          className="flex items-baseline justify-between gap-2"
          title="GET /api/restaurants - coveredPct = covered shifts / open shifts"
        >
          <dt className="text-steel">Coverage (14 d)</dt>
          <dd className="font-medium text-ink">{covered}%</dd>
        </div>
        <div
          className="flex items-baseline justify-between gap-2"
          title="GET /api/restaurants - openShifts minus covered shifts"
        >
          <dt className="text-steel">Coverage gap</dt>
          <dd className="font-medium text-ink">{coverageGap}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-2" title="GET /api/restaurants - bench">
          <dt className="text-steel">Bench</dt>
          <dd className="font-medium text-ink">{restaurant.bench}</dd>
        </div>
        <div
          className="flex items-baseline justify-between gap-2"
          title="GET /api/restaurants - openCandidates"
        >
          <dt className="text-steel">Open candidates</dt>
          <dd className="font-medium text-ink">{restaurant.openCandidates}</dd>
        </div>
        <div
          className="flex items-baseline justify-between gap-2"
          title="GET /api/restaurants - median time from shift proposal to manager decision"
        >
          <dt className="text-steel">Manager reply median</dt>
          <dd className="font-medium text-ink">
            {restaurant.managerMedianReply || "No manager decisions recorded"}
          </dd>
        </div>
      </dl>
    </Link>
  );
}

export function RestaurantsPage() {
  const { data, isError, error, refetch, isPending } = useQuery({
    queryKey: ["restaurants"],
    queryFn: fetchRestaurants,
  });

  return (
    <div className="min-w-0">
      <p className="text-micro font-semibold uppercase tracking-wide text-steel">
        Workspace
      </p>
      <h1 className="text-heading-3 font-semibold text-ink">Restaurants</h1>
      <p className="mt-1 text-body-sm text-steel">
        {data
          ? `${data.length} restaurants: coverage for the open shifts, bench and manager SLA`
          : "Loading restaurants"}
      </p>

      {isPending && (
        <p role="status" className="mt-6 text-body-sm text-steel">
          Loading restaurants
        </p>
      )}

      {isError && (
        <div role="alert" className="mt-6 rounded-lg border border-hairline bg-canvas p-6">
          <p className="text-body-sm-medium text-brand-error">Could not load restaurants</p>
          <p className="mt-1 text-body-sm text-steel">
            {error instanceof ApiError ? error.message : "Unknown error"}
          </p>
          <button
            type="button"
            onClick={() => refetch()}
            className="mt-4 flex h-11 items-center rounded-full border border-hairline px-4 text-body-sm-medium text-ink"
          >
            Retry
          </button>
        </div>
      )}

      {data && data.length === 0 && (
        <div className="mt-6 rounded-lg border border-hairline-soft bg-canvas p-8 text-center">
          <p className="text-body-sm-medium text-ink">No restaurants yet</p>
          <p className="mt-1 text-body-sm text-steel">
            Restaurants appear here once the client systems report their rota.
          </p>
        </div>
      )}

      {data && data.length > 0 && (
        <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {data.map((restaurant) => (
            <RestaurantCard key={restaurant.id} restaurant={restaurant} />
          ))}
        </div>
      )}
    </div>
  );
}

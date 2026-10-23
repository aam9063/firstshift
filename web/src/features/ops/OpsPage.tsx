import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  ApiError,
  fetchAdapterHealth,
  fetchEscalations,
  fetchOutbox,
  fetchRestaurants,
  pauseRestaurant,
  replayOutboxMessage,
} from "../../api/client";
import type { AdapterHealth, AttentionItem, OutboxMessageRow, RestaurantRow } from "../../api/types";

/* Operations queues (specs/04b-console.md section 3.6, odd/tasks/console-views.md
   T2/S2): manager decisions pending with the SLA countdown, unconfirmed first
   shifts, DLQ with replay, degraded adapters and paused restaurants. Every
   action sends X-Actor-Role: ops so the audit trail carries the role. */

function SectionCard({
  title,
  tooltip,
  count,
  children,
}: {
  title: string;
  tooltip?: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-hairline-soft bg-canvas p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-heading-5 font-semibold text-ink" title={tooltip}>
          {title}
          {count !== undefined && <span className="ml-2 text-body-sm font-normal text-steel">{count}</span>}
        </h2>
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function EmptyNote({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border border-hairline-soft bg-canvas p-6 text-center text-body-sm text-steel">{children}</p>;
}

function DecisionsQueue({ items }: { items: AttentionItem[] }) {
  return (
    <ul className="divide-y divide-hairline-soft">
      {items.map((item) => (
        <li key={item.id} className="flex flex-col gap-1 py-2.5 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-body-sm text-ink">{item.title}</p>
            <p className="text-caption text-steel">{item.detail}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span
              className="font-mono text-micro text-steel"
              title="GET /api/escalations - time waiting for the manager decision against the 24 h SLA"
            >
              {item.ago}
            </span>
            {item.kind === "sla_breach" && (
              <span
                className="rounded-sm bg-brand-error/10 px-1.5 py-0.5 text-micro font-semibold text-brand-error"
                title="GET /api/escalations - kind sla_breach: waiting longer than the 24 h manager SLA"
              >
                SLA breached
              </span>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

function DlqQueue() {
  const queryClient = useQueryClient();
  const [conflict, setConflict] = useState<string | null>(null);
  const { data, isError, error, isPending } = useQuery({
    queryKey: ["outbox", "failed"],
    queryFn: () => fetchOutbox("failed", "ops"),
  });

  const replay = useMutation({
    mutationFn: (id: string) => replayOutboxMessage(id),
    onSuccess: () => {
      setConflict(null);
      queryClient.invalidateQueries({ queryKey: ["outbox", "failed"] });
    },
    onError: (cause) => {
      setConflict(cause instanceof ApiError ? cause.message : "Unknown error");
    },
  });

  if (isPending) return <p role="status" className="text-body-sm text-steel">Loading dead-letter queue</p>;
  if (isError) return <EmptyNote>Could not load the dead-letter queue: {error instanceof ApiError ? error.message : "unknown error"}</EmptyNote>;

  return (
    <div>
      {conflict && (
        <p role="alert" className="mb-3 rounded-sm bg-brand-error/10 px-2 py-1.5 text-caption text-brand-error">
          {conflict}
        </p>
      )}
      {data.messages.length === 0 ? (
        <EmptyNote>Dead-letter queue is empty: every outbound write is delivered.</EmptyNote>
      ) : (
        <ul className="divide-y divide-hairline-soft">
          {data.messages.map((row: OutboxMessageRow) => (
            <li key={row.id} className="flex flex-col gap-2 py-2.5 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="text-body-sm text-ink">
                  {row.port} {row.operation}
                </p>
                <p className="text-caption text-brand-error">{row.lastError ?? "failed without a recorded error"}</p>
                <p className="font-mono text-micro text-stone">
                  {row.id} · idempotency key {row.idempotencyKey}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span
                  className="font-mono text-micro text-steel"
                  title="GET /api/outbox?status=failed - attempts"
                >
                  {row.attempts} attempts
                </span>
                <button
                  type="button"
                  onClick={() => replay.mutate(row.id)}
                  disabled={replay.isPending}
                  className="flex h-9 items-center rounded-full border border-hairline px-3 text-caption font-medium text-ink disabled:opacity-50"
                  title="POST /api/outbox/{id}/replay - resets the row to pending for the relay"
                >
                  {replay.isPending ? "Replaying..." : "Replay"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AdaptersQueue() {
  const { data, isError, isPending } = useQuery({
    queryKey: ["adapters"],
    queryFn: fetchAdapterHealth,
  });

  if (isPending) return <p role="status" className="text-body-sm text-steel">Loading adapter health</p>;
  if (isError || !data) return <EmptyNote>Could not load adapter health.</EmptyNote>;

  const degraded = data.adapters.filter((adapter) => adapter.status === "degraded");
  return (
    <div>
      <p
        className="text-caption text-steel"
        title="GET /health/adapters - status ok, degraded or unknown per client system"
      >
        {degraded.length} degraded of {data.adapters.length} client systems
      </p>
      <ul className="mt-2 divide-y divide-hairline-soft">
        {data.adapters.map((adapter: AdapterHealth) => (
          <li key={adapter.system} className="flex flex-col gap-1 py-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="font-mono text-caption text-ink">{adapter.system}</p>
              {adapter.failureReason && <p className="text-caption text-steel">{adapter.failureReason}</p>}
            </div>
            {adapter.status === "degraded" ? (
              <span
                className="w-fit rounded-sm bg-brand-warn/15 px-1.5 py-0.5 text-micro font-semibold text-charcoal"
                title="GET /health/adapters - status degraded: the probe failed or timed out"
              >
                Degraded
              </span>
            ) : (
              <span
                className="w-fit rounded-sm bg-surface px-1.5 py-0.5 font-mono text-micro text-steel"
                title="GET /health/adapters - status unknown: no health probe implemented"
              >
                {adapter.status}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function RestaurantsQueue() {
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);
  const { data, isError, isPending } = useQuery({
    queryKey: ["restaurants"],
    queryFn: fetchRestaurants,
  });

  const toggle = useMutation({
    mutationFn: ({ id, resume }: { id: string; resume: boolean }) =>
      pauseRestaurant(id, { resume }),
    onSuccess: () => {
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["restaurants"] });
    },
    onError: (cause) =>
      setActionError(cause instanceof ApiError ? cause.message : "Unknown error"),
  });

  if (isPending) return <p role="status" className="text-body-sm text-steel">Loading restaurants</p>;
  if (isError || !data) return <EmptyNote>Could not load restaurants.</EmptyNote>;

  const paused = data.filter((restaurant) => restaurant.paused);
  return (
    <div>
      {actionError && (
        <p role="alert" className="mb-3 rounded-sm bg-brand-error/10 px-2 py-1.5 text-caption text-brand-error">
          {actionError}
        </p>
      )}
      {paused.length === 0 ? (
        <EmptyNote>No restaurants are paused: every agent flow is running.</EmptyNote>
      ) : (
        <ul className="divide-y divide-hairline-soft">
          {paused.map((restaurant: RestaurantRow) => (
            <li key={restaurant.id} className="flex items-center justify-between gap-2 py-2.5">
              <div>
                <p className="text-body-sm text-ink">{restaurant.name}</p>
                <p className="font-mono text-micro text-stone">
                  {restaurant.code} · {restaurant.city}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className="rounded-sm bg-brand-warn/15 px-1.5 py-0.5 text-micro font-semibold text-charcoal"
                  title="GET /api/restaurants - paused: all agent flows for this restaurant are stopped"
                >
                  Paused
                </span>
                <button
                  type="button"
                  onClick={() => toggle.mutate({ id: restaurant.id, resume: true })}
                  disabled={toggle.isPending}
                  className="flex h-9 items-center rounded-full border border-hairline px-3 text-caption font-medium text-ink disabled:opacity-50"
                  title="POST /api/restaurants/{id}/pause with resume true - runbook operation"
                >
                  Resume
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function OpsPage() {
  const { data: escalations, isError, error, isPending } = useQuery({
    queryKey: ["escalations"],
    queryFn: fetchEscalations,
  });

  const decisions = (escalations ?? []).filter(
    (item) => item.kind === "human_needed" || item.kind === "sla_breach",
  );
  const firstShifts = (escalations ?? []).filter((item) => item.kind === "first_shift");

  return (
    <div className="min-w-0">
      <p className="text-micro font-semibold uppercase tracking-wide text-steel">Operations</p>
      <h1 className="text-heading-3 font-semibold text-ink">Escalations and operations</h1>
      <p className="mt-1 text-body-sm text-steel">
        Queues for the runbook. Actions are audited with X-Actor-Role: ops.
      </p>

      <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <SectionCard
          title="Manager decisions pending"
          tooltip="GET /api/escalations - applications in pending_manager_decision, 24 h SLA"
          count={isPending ? undefined : decisions.length}
        >
          {isPending ? (
            <p role="status" className="text-body-sm text-steel">Loading escalations</p>
          ) : isError ? (
            <EmptyNote>Could not load escalations: {error instanceof ApiError ? error.message : "unknown error"}</EmptyNote>
          ) : decisions.length === 0 ? (
            <EmptyNote>No manager decisions are pending: every queue is inside its SLA.</EmptyNote>
          ) : (
            <DecisionsQueue items={decisions} />
          )}
        </SectionCard>

        <SectionCard
          title="First shifts unconfirmed"
          tooltip="GET /api/escalations - first shifts scheduled in the next 48 h without confirmation"
          count={isPending ? undefined : firstShifts.length}
        >
          {isPending ? (
            <p role="status" className="text-body-sm text-steel">Loading escalations</p>
          ) : isError ? (
            <EmptyNote>Could not load escalations.</EmptyNote>
          ) : firstShifts.length === 0 ? (
            <EmptyNote>No first shifts are waiting for confirmation.</EmptyNote>
          ) : (
            <DecisionsQueue items={firstShifts} />
          )}
        </SectionCard>

        <SectionCard title="Escalated conversations">
          <EmptyNote>
            The escalated conversations queue has no dedicated endpoint yet: conversations
            escalated to a human appear as manager decisions pending above.
          </EmptyNote>
        </SectionCard>

        <SectionCard
          title="Dead-letter queue"
          tooltip="GET /api/outbox?status=failed, replay with POST /api/outbox/{id}/replay"
        >
          <DlqQueue />
        </SectionCard>

        <SectionCard title="Adapters" tooltip="GET /health/adapters - per client system probe">
          <AdaptersQueue />
        </SectionCard>

        <SectionCard
          title="Paused restaurants"
          tooltip="GET /api/restaurants - paused; resume with POST /api/restaurants/{id}/pause"
        >
          <RestaurantsQueue />
        </SectionCard>
      </div>
    </div>
  );
}

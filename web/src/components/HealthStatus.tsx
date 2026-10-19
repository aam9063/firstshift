import { useQuery } from "@tanstack/react-query";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

interface HealthResponse {
  status: string;
  service: string;
}

async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_URL}/health`);
  if (!response.ok) {
    throw new Error(`Backend answered ${response.status}`);
  }
  return response.json() as Promise<HealthResponse>;
}

export function HealthStatus() {
  const { data, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    retry: false,
  });

  const status = isError ? "unavailable" : (data?.status ?? "checking");

  return (
    <section className="rounded-lg border border-hairline p-6">
      <h2 className="text-sm font-medium text-ink">Backend health</h2>
      <p className="mt-2 text-sm text-steel">
        FirstShift API at <code className="font-mono">{API_URL}</code>
      </p>
      <span
        data-testid="health-status"
        className={`mt-4 inline-block rounded-sm px-2 py-1 font-mono text-sm ${
          status === "ok"
            ? "bg-brand-green-soft text-brand-green-deep"
            : "bg-brand-error/10 text-brand-error"
        }`}
      >
        {status}
      </span>
    </section>
  );
}

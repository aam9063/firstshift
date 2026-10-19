import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { HealthStatus } from "./components/HealthStatus";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route
            path="/"
            element={
              <main className="mx-auto max-w-3xl p-8">
                <h1 className="text-xl font-semibold text-ink">FirstShift</h1>
                <p className="mt-1 text-sm text-steel">
                  From staffing gap to first productive shift.
                </p>
                <div className="mt-6">
                  <HealthStatus />
                </div>
              </main>
            }
          />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

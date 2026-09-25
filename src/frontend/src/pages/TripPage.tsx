import { Link, NavLink, Outlet, useLocation, useOutletContext, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTrip } from "@/hooks/useTrip";
import { useGenerationJob } from "@/hooks/useGenerationJob";
import { warningStages } from "@/lib/generationJob";
import { api } from "@/lib/api";
import { tripDetailShell, type TripDetailShell } from "@/lib/tripDetailState";
import ChatPanel from "@/components/ChatPanel";
import TripDetail, { TripIdentityHeader } from "@/components/TripDetail";
import TripStatusShell from "@/components/TripStatusShell";
import type { Trip } from "@/lib/types";

export type TripOutletContext = { trip: Trip };

export function useTripOutlet() {
  return useOutletContext<TripOutletContext>();
}

function tabClass({ isActive }: { isActive: boolean }) {
  return `inline-flex min-h-9 items-center rounded-full px-4 text-sm font-medium transition duration-200 ${
    isActive
      ? "bg-blue-600 text-white"
      : "border border-line-tertiary bg-elevated text-ink-secondary hover:text-ink"
  }`;
}

function readableRetryError(error: unknown): string {
  const message = error instanceof Error ? error.message : "";
  if (!message || message === "Trip not found") return "没有找到这趟行程，无法重新生成";
  if (message.startsWith("API error")) return "重新生成没有成功，请稍后再试";
  return message;
}

export default function TripPage() {
  const { tripId } = useParams<{ tripId: string }>();
  const location = useLocation();
  const isMap = /\/map\/?$/.test(location.pathname);
  const queryClient = useQueryClient();
  const { data: trip, isLoading, isError } = useTrip(tripId ?? "");
  const { job, progress } = useGenerationJob(tripId, trip?.status);
  const shell: TripDetailShell | null = trip ? tripDetailShell(trip) : null;
  const warnings = warningStages(job, progress);
  const retry = useMutation({
    mutationFn: () => api.post<Trip>(`/trips/${tripId}/retry`, {}),
    onSuccess: (data) => {
      queryClient.setQueryData(["trip", tripId], data);
      queryClient.removeQueries({ queryKey: ["progress", tripId] });
    },
  });

  const tabs = tripId && shell === "ready" ? (
    <nav aria-label="行程视图" className="flex flex-wrap items-center gap-1">
      <NavLink to={`/trips/${tripId}`} end className={tabClass}>
        行程
      </NavLink>
      <NavLink to={`/trips/${tripId}/map`} className={tabClass}>
        回忆
      </NavLink>
    </nav>
  ) : null;

  const backLink = (
    <Link
      to="/trips"
      className="inline-flex min-h-9 shrink-0 items-center rounded-full border border-line-tertiary bg-elevated px-3 text-sm text-ink-secondary hover:text-ink"
    >
      ← 我的行程
    </Link>
  );

  if (trip && shell && shell !== "ready") {
    return (
      <main className="min-h-screen bg-chrome px-4 pb-16 pt-5 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-3xl">
          <div className="mb-4">{backLink}</div>
          <TripIdentityHeader trip={trip} shell={shell} />
          <TripStatusShell
            trip={trip}
            shell={shell}
            job={job}
            progress={progress}
            retrying={retry.isPending}
            retryError={retry.isError ? readableRetryError(retry.error) : null}
            onRetry={() => retry.mutate()}
          />
        </div>
      </main>
    );
  }

  if (isMap) {
    return (
      <div className="relative h-dvh overflow-hidden bg-chrome">
        <div className="pointer-events-none absolute inset-x-0 top-0 z-30 p-3 pt-[max(0.75rem,env(safe-area-inset-top))] sm:p-4">
          <div className="pointer-events-auto mx-auto flex max-w-5xl flex-wrap items-center gap-3 rounded-2xl border border-line-tertiary bg-elevated/90 px-3 py-2 shadow-sm backdrop-blur-md">
            {backLink}
            {trip && (
              <h1 className="min-w-0 flex-1 truncate text-base font-semibold text-ink">
                {trip.destination}
              </h1>
            )}
            {tabs}
          </div>
        </div>
        {tripId === "demo" && (
          <p className="absolute left-4 top-24 z-20 text-ink-tertiary">请从首页创建真实行程后再查看。</p>
        )}
        {isLoading && <p className="absolute left-4 top-24 z-20 text-ink-tertiary">正在加载行程…</p>}
        {isError && (
          <p className="absolute left-4 top-24 z-20 text-rose-700">加载失败，请确认行程 ID 是否正确。</p>
        )}
        {trip && <Outlet context={{ trip } satisfies TripOutletContext} />}
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-chrome px-4 pb-16 pt-5 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          {backLink}
          {trip && (
            <h1 className="min-w-0 flex-1 truncate text-base font-semibold text-ink">
              {trip.destination}
            </h1>
          )}
          {tabs}
        </div>

        {tripId === "demo" && (
          <p className="rounded-2xl border border-dashed border-line-tertiary bg-elevated px-4 py-8 text-center text-sm text-ink-tertiary">
            请从首页创建真实行程后再查看。
          </p>
        )}

        {isLoading && (
          <p className="rounded-2xl border border-dashed border-line-tertiary bg-elevated px-4 py-8 text-center text-sm text-ink-tertiary">
            正在加载行程…
          </p>
        )}
        {isError && (
          <p className="rounded-2xl border border-line-tertiary bg-rose-50 px-4 py-8 text-center text-sm text-rose-700">
            加载失败，请确认行程 ID 是否正确，或检查后端服务是否启动。
          </p>
        )}

        {trip && shell === "ready" && (
          <>
            <TripIdentityHeader trip={trip} shell={shell} />
            {warnings.length > 0 && (
              <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 p-4">
                <p className="text-sm font-medium text-amber-800">时效风险</p>
                <ul className="mt-2 space-y-1 text-xs text-amber-800">
                  {warnings.map((stage, index) => (
                    <li key={`${stage.key}-${stage.at}-${index}`}>{stage.message}</li>
                  ))}
                </ul>
              </div>
            )}
            <Outlet context={{ trip } satisfies TripOutletContext} />
          </>
        )}
      </div>
    </main>
  );
}

export function TripItineraryPage() {
  const { trip } = useTripOutlet();
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
      <TripDetail trip={trip} />
      <div className="lg:sticky lg:top-4 lg:self-start">
        <ChatPanel tripId={trip.id} />
      </div>
    </div>
  );
}

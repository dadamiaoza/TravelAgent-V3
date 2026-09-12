import { Link, NavLink, Outlet, useLocation, useOutletContext, useParams } from "react-router-dom";
import { useTrip } from "@/hooks/useTrip";
import { useGenerationJob } from "@/hooks/useGenerationJob";
import { warningStages } from "@/lib/generationJob";
import ChatPanel from "@/components/ChatPanel";
import GenerationProgressBanner from "@/components/GenerationProgressBanner";
import TripDetail from "@/components/TripDetail";
import type { Trip } from "@/lib/types";

export type TripOutletContext = { trip: Trip };

export function useTripOutlet() {
  return useOutletContext<TripOutletContext>();
}

function tabClass({ isActive }: { isActive: boolean }) {
  return `inline-flex min-h-11 items-center rounded-full px-4 text-sm font-medium transition duration-200 ${
    isActive
      ? "bg-sky-600 text-white"
      : "text-slate-600 hover:bg-white/70 hover:text-slate-900"
  }`;
}

export default function TripPage() {
  const { tripId } = useParams<{ tripId: string }>();
  const location = useLocation();
  const isMap = /\/map\/?$/.test(location.pathname);
  const { data: trip, isLoading, isError } = useTrip(tripId ?? "");
  const { job, progress } = useGenerationJob(tripId, trip?.status);
  const isGenerating = trip?.status === "generating";
  const isFailed =
    trip?.status === "generation_failed" || job?.status === "failed";
  const warnings = warningStages(job, progress);

  const tabs = tripId ? (
    <nav aria-label="行程视图" className="flex flex-wrap items-center gap-1">
      <NavLink to={`/trips/${tripId}`} end className={tabClass}>
        行程
      </NavLink>
      <NavLink to={`/trips/${tripId}/map`} className={tabClass}>
        地图
      </NavLink>
      <span
        title="下一期"
        className="inline-flex min-h-11 cursor-not-allowed items-center rounded-full px-4 text-sm text-slate-400"
      >
        照片
      </span>
    </nav>
  ) : null;

  if (isMap) {
    return (
      <div className="relative h-dvh overflow-hidden bg-sky-50">
        <div className="pointer-events-none absolute inset-x-0 top-0 z-30 p-3 pt-[max(0.75rem,env(safe-area-inset-top))] sm:p-4">
          <div className="pointer-events-auto mx-auto flex max-w-5xl flex-wrap items-center gap-3 rounded-2xl border border-white/70 bg-white/75 px-3 py-2 shadow-sm backdrop-blur-md">
            <Link
              to="/"
              className="min-h-11 shrink-0 rounded-full px-3 text-sm text-sky-700 hover:bg-white"
            >
              返回首页
            </Link>
            {trip && (
              <h1 className="min-w-0 flex-1 truncate text-base font-semibold text-slate-900">
                {trip.destination}
              </h1>
            )}
            {tabs}
          </div>
        </div>
        {tripId === "demo" && (
          <p className="absolute left-4 top-24 z-20 text-slate-500">请从首页创建真实行程后再查看。</p>
        )}
        {isLoading && <p className="absolute left-4 top-24 z-20 text-slate-500">正在加载行程…</p>}
        {isError && (
          <p className="absolute left-4 top-24 z-20 text-red-600">加载失败，请确认行程 ID 是否正确。</p>
        )}
        {trip && <Outlet context={{ trip } satisfies TripOutletContext} />}
      </div>
    );
  }

  return (
    <main className="mx-auto max-w-7xl p-8">
      <Link to="/" className="mb-4 inline-block text-blue-600 hover:underline">
        &larr; 返回首页
      </Link>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-bold">行程详情</h1>
        {tabs}
      </div>

      {tripId === "demo" && (
        <p className="text-gray-500">请从首页创建真实行程后再查看。</p>
      )}

      {isLoading && <p className="text-gray-500">正在加载行程…</p>}
      {isError && (
        <p className="text-red-600">
          加载失败，请确认行程 ID 是否正确，或检查后端服务是否启动。
        </p>
      )}
      {trip && isGenerating && (
        <GenerationProgressBanner job={job} progress={progress} />
      )}
      {trip && isFailed && !isGenerating && (
        <GenerationProgressBanner job={job} progress={progress} failed />
      )}
      {trip && !isGenerating && !isFailed && warnings.length > 0 && (
        <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm font-medium text-amber-800">时效风险</p>
          <ul className="mt-2 space-y-1 text-xs text-amber-800">
            {warnings.map((stage, index) => (
              <li key={`${stage.key}-${stage.at}-${index}`}>{stage.message}</li>
            ))}
          </ul>
        </div>
      )}

      {trip && <Outlet context={{ trip } satisfies TripOutletContext} />}
    </main>
  );
}

export function TripItineraryPage() {
  const { trip } = useTripOutlet();
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
      <TripDetail trip={trip} />
      <div className="h-fit lg:sticky lg:top-4">
        <ChatPanel tripId={trip.id} />
      </div>
    </div>
  );
}

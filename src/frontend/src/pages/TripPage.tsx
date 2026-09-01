import { useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTrip } from "@/hooks/useTrip";
import { api } from "@/lib/api";
import type { GenerationProgress } from "@/lib/types";
import TripDetail from "@/components/TripDetail";
import ChatPanel from "@/components/ChatPanel";

export default function TripPage() {
  const { tripId } = useParams<{ tripId: string }>();
  const { data: trip, isLoading, isError } = useTrip(tripId ?? "");
  const queryClient = useQueryClient();

  const { data: progress } = useQuery<GenerationProgress>({
    queryKey: ["progress", tripId],
    queryFn: () => api.get<GenerationProgress>(`/trips/${tripId}/progress`),
    enabled: !!tripId && trip?.status === "generating",
    refetchInterval: 1000,
  });

  useEffect(() => {
    if (progress?.status === "generated") {
      queryClient.invalidateQueries({ queryKey: ["trip", tripId] });
    }
  }, [progress, tripId, queryClient]);

  return (
    <main className="mx-auto max-w-7xl p-8">
      <Link to="/" className="text-blue-600 hover:underline mb-4 inline-block">
        &larr; 返回首页
      </Link>
      <h1 className="text-2xl font-bold mb-4">行程详情</h1>

      {tripId === "demo" && (
        <p className="text-gray-500">请从首页创建真实行程后再查看。</p>
      )}

      {isLoading && <p className="text-gray-500">正在加载行程…</p>}
      {isError && (
        <p className="text-red-600">
          加载失败，请确认行程 ID 是否正确，或检查后端服务是否启动。
        </p>
      )}
      {trip && trip.status === "generating" && (
        <div className="mb-6 rounded-lg border border-blue-200 bg-blue-50 p-4">
          <p className="text-sm text-blue-700">{progress?.message ?? "正在生成行程…"}</p>
          <div className="mt-2 h-2 w-full overflow-hidden rounded bg-blue-100">
            <div
              className="h-full rounded bg-blue-600 transition-all"
              style={{ width: `${progress?.progress ?? 0}%` }}
            />
          </div>
        </div>
      )}

      {trip && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
          <TripDetail trip={trip} />
          <div className="h-fit lg:sticky lg:top-4">
            <ChatPanel tripId={trip.id} />
          </div>
        </div>
      )}
    </main>
  );
}

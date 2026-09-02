import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useTrip } from "@/hooks/useTrip";
import type { GenerationProgress } from "@/lib/types";
import TripDetail from "@/components/TripDetail";
import ChatPanel from "@/components/ChatPanel";

export default function TripPage() {
  const { tripId } = useParams<{ tripId: string }>();
  const { data: trip, isLoading, isError } = useTrip(tripId ?? "");
  const queryClient = useQueryClient();
  const [progress, setProgress] = useState<GenerationProgress | null>(null);

  useEffect(() => {
    if (!tripId || trip?.status !== "generating") return;

    const source = new EventSource(`/api/v1/trips/${tripId}/progress/stream`);

    source.addEventListener("progress", (event) => {
      try {
        setProgress(JSON.parse(event.data));
      } catch {
        // ignore malformed progress events
      }
    });

    source.addEventListener("done", (event) => {
      try {
        setProgress(JSON.parse(event.data));
      } catch {
        // ignore
      }
      queryClient.invalidateQueries({ queryKey: ["trip", tripId] });
      source.close();
    });

    source.onerror = () => {
      source.close();
    };

    return () => source.close();
  }, [tripId, trip?.status, queryClient]);

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

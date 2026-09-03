import { useParams, Link } from "react-router-dom";
import { useTrip } from "@/hooks/useTrip";
import { useGenerationJob } from "@/hooks/useGenerationJob";
import TripDetail from "@/components/TripDetail";
import ChatPanel from "@/components/ChatPanel";

export default function TripPage() {
  const { tripId } = useParams<{ tripId: string }>();
  const { data: trip, isLoading, isError } = useTrip(tripId ?? "");
  const { job } = useGenerationJob(tripId, trip?.status);
  const isGenerating = trip?.status === "generating";
  const isFailed =
    trip?.status === "generation_failed" || job?.status === "failed";

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
      {trip && isGenerating && (
        <div className="mb-6 rounded-lg border border-blue-200 bg-blue-50 p-4">
          <p className="text-sm text-blue-700">{job?.message ?? "正在生成行程…"}</p>
          <div className="mt-2 h-2 w-full overflow-hidden rounded bg-blue-100">
            <div
              className="h-full rounded bg-blue-600 transition-all"
              style={{ width: `${job?.progress ?? 0}%` }}
            />
          </div>
        </div>
      )}
      {trip && isFailed && !isGenerating && (
        <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-700">
            {job?.message ?? "行程生成失败，请稍后重试"}
          </p>
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

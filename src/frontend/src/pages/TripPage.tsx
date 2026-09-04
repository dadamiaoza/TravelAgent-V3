import { useParams, Link } from "react-router-dom";
import { useTrip } from "@/hooks/useTrip";
import { useGenerationJob } from "@/hooks/useGenerationJob";
import TripDetail from "@/components/TripDetail";
import ChatPanel from "@/components/ChatPanel";
import GenerationProgressBanner from "@/components/GenerationProgressBanner";

export default function TripPage() {
  const { tripId } = useParams<{ tripId: string }>();
  const { data: trip, isLoading, isError } = useTrip(tripId ?? "");
  const { job, progress } = useGenerationJob(tripId, trip?.status);
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
        <GenerationProgressBanner job={job} progress={progress} />
      )}
      {trip && isFailed && !isGenerating && (
        <GenerationProgressBanner job={job} progress={progress} failed />
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

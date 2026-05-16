import { useParams, Link } from "react-router-dom";

export default function TripPage() {
  const { tripId } = useParams<{ tripId: string }>();

  return (
    <main className="max-w-4xl mx-auto p-8">
      <Link to="/" className="text-primary hover:underline mb-4 inline-block">
        &larr; 返回首页
      </Link>
      <h1 className="text-2xl font-bold mb-4">行程详情</h1>
      <p className="text-muted-foreground">行程 ID: {tripId}</p>
    </main>
  );
}

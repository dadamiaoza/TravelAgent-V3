import TripCreateForm from "@/components/TripCreateForm";

export default function HomePage() {
  return (
    <main className="max-w-2xl mx-auto p-8">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold text-gray-900">AI 旅行规划助手</h1>
        <p className="mt-2 text-gray-500">
          填写基本信息，自动生成你的 Day-by-Day 行程
        </p>
      </div>
      <TripCreateForm />
    </main>
  );
}

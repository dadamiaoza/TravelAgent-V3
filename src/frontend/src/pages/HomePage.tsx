import { Link } from "react-router-dom";

export default function HomePage() {
  return (
    <main className="max-w-4xl mx-auto p-8">
      <h1 className="text-3xl font-bold mb-4">AI 旅行规划助手</h1>
      <p className="text-muted-foreground mb-8">
        导入攻略、生成行程、一键优化路线
      </p>
      <Link
        to="/trips/demo"
        className="inline-block px-6 py-3 bg-primary text-primary-foreground rounded-lg"
      >
        创建新行程
      </Link>
    </main>
  );
}

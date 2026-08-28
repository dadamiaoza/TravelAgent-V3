import { Routes, Route } from "react-router-dom";
import HomePage from "@/pages/HomePage";
import TripPage from "@/pages/TripPage";
import SourcePage from "@/pages/SourcePage";

export default function App() {
  return (
    <div className="min-h-screen bg-background">
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/trips/:tripId" element={<TripPage />} />
        <Route path="/sources" element={<SourcePage />} />
      </Routes>
    </div>
  );
}

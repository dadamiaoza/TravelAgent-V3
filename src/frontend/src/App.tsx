import { Routes, Route } from "react-router-dom";
import HomePage from "@/pages/HomePage";
import MyTripsPage from "@/pages/MyTripsPage";
import TripPage, { TripItineraryPage } from "@/pages/TripPage";
import TripMapPage from "@/pages/TripMapPage";
import SourcePage from "@/pages/SourcePage";

export default function App() {
  return (
    <div className="min-h-screen bg-background">
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/trips" element={<MyTripsPage />} />
        <Route path="/trips/:tripId" element={<TripPage />}>
          <Route index element={<TripItineraryPage />} />
          <Route path="map" element={<TripMapPage />} />
        </Route>
        <Route path="/sources" element={<SourcePage />} />
      </Routes>
    </div>
  );
}

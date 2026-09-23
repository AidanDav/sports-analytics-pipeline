import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Teams from "./pages/Teams";
import Games from "./pages/Games";
import Players from "./pages/Players";
import Reports from "./pages/Reports";
import ReportDetail from "./pages/ReportDetail";
import TeamDetail from "./pages/TeamDetail";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="teams" element={<Teams />} />
        <Route path="teams/:id" element={<TeamDetail />} />
        <Route path="games" element={<Games />} />
        <Route path="players" element={<Players />} />
        <Route path="reports" element={<Reports />} />
        <Route path="reports/:id" element={<ReportDetail />} />
      </Route>
    </Routes>
  );
}
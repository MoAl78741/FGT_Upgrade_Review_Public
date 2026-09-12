import { Routes, Route } from "react-router-dom";
import {TeamProvider, WorkspaceBar, useTeam} from "./contexts/TeamContext";
import Account from "./pages/Account";
import Installation from "./pages/Installation";
import Breadcrumbs from "./components/Breadcrumbs";
import Header from "./components/Header";
import Home from "./pages/Home";
import Reviews from "./pages/Reviews";
import ReviewPage from "./pages/Review";
import Report from "./pages/Report";

export default function App() {
  return <TeamProvider><AppContent /></TeamProvider>;
}
function AppContent() {
  const team = useTeam();
  const assigned = !team.enabled || !!team.role;
  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <WorkspaceBar />
      <main className="flex-1" id="main-content">
        <Breadcrumbs />
        <Routes>
          <Route path="/installation" element={<Installation />} />
          <Route path="/account" element={<Account />} />
          <Route path="/" element={assigned ? <Home /> : <NoWorkspace />} />
          <Route path="/reviews" element={assigned ? <Reviews /> : <NoWorkspace />} />
          <Route path="/reviews/:id" element={assigned ? <ReviewPage /> : <NoWorkspace />} />
          <Route path="/reports/:id" element={assigned ? <Report /> : <NoWorkspace />} />
        </Routes>
      </main>
    </div>
  );
}

function NoWorkspace() {
  return <p className="max-w-lg mx-auto p-8 text-gray-300">Choose an assigned customer workspace above. If none are listed, ask your installation administrator to assign access. You can still manage your password from Account.</p>;
}

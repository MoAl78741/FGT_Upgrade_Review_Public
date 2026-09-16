import { Routes, Route } from "react-router-dom";
import {TeamProvider, WorkspaceBar, useTeam} from "./contexts/TeamContext";
import Administration from "./pages/Administration";
import Account from "./pages/Account";
import Installation from "./pages/Installation";
import Breadcrumbs from "./components/Breadcrumbs";
import Header from "./components/Header";
import Home from "./pages/Home";
import Pro from "./pages/Pro";
import Example from "./pages/Example";
import ReportLibrary from "./components/ReportLibrary";
import Reviews from "./pages/Reviews";
import ReviewPage from "./pages/Review";
import Report from "./pages/Report";

export default function App() {
  return <TeamProvider><AppContent /></TeamProvider>;
}
function AppContent() {
  const team = useTeam();
  const assigned = !team.enabled || !!team.role;
  const can = (permission:string) => !team.enabled || !!team.permissions?.includes(permission);
  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <WorkspaceBar />
      <main className="flex-1" id="main-content">
        <Breadcrumbs />
        <Routes>
          <Route path="/pro" element={<Pro />} />
          <Route path="/example" element={<Example />} />
          <Route path="/library" element={assigned && can("reports.read") ? <ReportLibrary /> : <NoWorkspace />} />
          <Route path="/administration" element={<Administration />} />
          <Route path="/installation" element={<Installation />} />
          <Route path="/account" element={<Account />} />
          <Route path="/" element={assigned && can("reports.read") ? <Home /> : <NoWorkspace />} />
          <Route path="/reviews" element={assigned && can("reviews.read") ? <Reviews /> : <NoWorkspace />} />
          <Route path="/reviews/:id" element={assigned && can("reviews.read") ? <ReviewPage /> : <NoWorkspace />} />
          <Route path="/reports/:id" element={assigned && can("reports.read") ? <Report /> : <NoWorkspace />} />
        </Routes>
      </main>
      <footer className="max-w-screen-xl mx-auto w-full px-6 py-6 text-sm text-gray-400 flex flex-wrap gap-5"><a href="/api/docs">API documentation</a><a href="/installation">Help & support</a><a href="/administration">Operator administration</a><span>Independent project · Not affiliated with Fortinet</span></footer>
    </div>
  );
}

function NoWorkspace() {
  return <p className="max-w-lg mx-auto p-8 text-gray-300">Choose an assigned domain with permission to view this page. Ask your installation administrator to update your access profile if needed. You can still manage your password from Account.</p>;
}

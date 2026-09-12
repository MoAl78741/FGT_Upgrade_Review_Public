import {useTeam} from "../contexts/TeamContext";
import {Link} from "react-router-dom";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Database, Globe, FileText } from "lucide-react";
import { api } from "../api";
import NewScrapeForm from "../components/NewScrapeForm";
import PdfUploadForm from "../components/PdfUploadForm";
import JobCard from "../components/JobCard";
import type { Job } from "../types";

type InputTab = "scrape" | "pdf";

export default function Home() {
  const team = useTeam();
  const [activeTab, setActiveTab] = useState<InputTab>("pdf");

  const {data: capabilities} = useQuery({queryKey: ["capabilities"], queryFn: api.capabilities});

  const { data: jobs, isLoading, error } = useQuery({
    queryKey: ["jobs"],
    queryFn: api.listJobs,
    refetchInterval: 5000,
  });

  const activeCount = jobs?.filter((j: Job) => ["running", "pending", "uploading"].includes(j.status)).length ?? 0;
  const completedCount = jobs?.filter((j: Job) => j.status === "completed").length ?? 0;

  return (
    <div className="max-w-screen-xl mx-auto px-6 py-8 space-y-8">
      <section aria-labelledby="home-title" className="space-y-4">
        <div><h1 id="home-title" className="text-2xl font-semibold text-white">Home</h1><p className="mt-2 text-gray-300">Import release notes, open your reports, and prepare an upgrade review.</p></div>
        <div className="grid sm:grid-cols-3 gap-3">
          <a href="#import" className="block bg-navy-800 border border-navy-600 rounded-xl p-4 hover:border-brand-500"><h2 className="font-semibold text-brand-500">1. Import release notes</h2><p className="text-sm text-gray-300 mt-2">Upload PDFs{capabilities?.scraping ? ' or scrape documentation' : ''}. Each batch creates a source report.</p></a>
          <a href="#reports" className="block bg-navy-800 border border-navy-600 rounded-xl p-4 hover:border-brand-500"><h2 className="font-semibold text-brand-500">2. Open your reports</h2><p className="text-sm text-gray-300 mt-2">Read the imported notes, compare versions, check completeness, and export the source content.</p></a>
          <Link to="/reviews" className="block bg-navy-800 border border-navy-600 rounded-xl p-4 hover:border-brand-500"><h2 className="font-semibold text-brand-500">3. Prepare an upgrade review</h2><p className="text-sm text-gray-300 mt-2">Optional: combine reports for one upgrade, record decisions and testing tasks, then export your review.</p></Link>
        </div>
      </section>
      <div id="import" className="scroll-mt-72 space-y-4">
      <h2 className="text-lg font-semibold text-white">Import release notes</h2>
      {/* Tab switcher */}
      <div className="flex gap-1 p-1 bg-navy-800 border border-navy-700 rounded-xl w-fit">
        {([ ["scrape", Globe, "Scrape"], ["pdf", FileText, "Upload PDFs"] ] as [InputTab, React.ElementType, string][]).filter(([id]) => id === "pdf" || capabilities?.scraping).map(
          ([id, Icon, label]) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-150 ${
                activeTab === id
                  ? "text-white"
                  : "text-gray-500 hover:text-gray-300"
              }`}
              style={
                activeTab === id
                  ? {
                      background: "rgb(var(--accent) / 0.15)",
                      border: "1px solid rgb(var(--accent) / 0.3)",
                      color: "rgb(var(--accent))",
                    }
                  : undefined
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          )
        )}
      </div>

      <p className="text-sm text-gray-400">{capabilities?.edition === 'public' ? 'Private session: PDFs and reports expire after 24 hours. Download results before leaving; clearing cookies loses access. Only upload documents you are authorized to process.' : 'Private edition: PDFs and reports stay on this installation. Scraping requires operator configuration.'}</p>
      {team.enabled && team.role === "viewer" ? <p className="text-gray-400">View-only access: open existing reports or reviews. A reviewer can import new documents.</p> : activeTab === "scrape" && capabilities?.scraping ? <NewScrapeForm /> : <PdfUploadForm />}

      </div>
      <section id="reports" className="scroll-mt-72">
        {/* Section header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-gray-500" />
            <h2 className="text-white font-semibold text-sm tracking-wide uppercase">
              Reports & processing
            </h2>
          </div>
          {jobs && jobs.length > 0 && (
            <div className="flex items-center gap-2 ml-1">
              {completedCount > 0 && (
                <span className="text-xs text-gray-500 bg-navy-800 border border-navy-700 px-2 py-0.5 rounded font-mono">
                  {completedCount} completed
                </span>
              )}
              {activeCount > 0 && (
                <span
                  className="text-xs px-2 py-0.5 rounded font-mono font-medium"
                  style={{
                    color: "rgb(var(--accent))",
                    background: "rgb(var(--accent) / 0.1)",
                    border: "1px solid rgb(var(--accent) / 0.25)",
                  }}
                >
                  {activeCount} active
                </span>
              )}
            </div>
          )}
          <div className="flex-1 h-px bg-navy-700 ml-2" />
        </div>

        <p className="text-sm text-gray-300 mb-4">Each entry is an import batch. Open its report to read the release notes, or add it to an upgrade review to record your decisions.</p>
        {isLoading && (
          <div className="flex items-center gap-2.5 text-gray-400 text-sm py-10">
            <Loader2 className="w-4 h-4 animate-spin text-brand-500" />
            <span>Loading reports…</span>
          </div>
        )}

        {error && (
          <div className="text-red-400 text-sm py-3 px-4 bg-red-900/20 border border-red-800/40 rounded-lg">
            Failed to load reports: {(error as Error).message}
          </div>
        )}

        {jobs && jobs.length === 0 && (
          <div className="py-12 text-center border border-dashed border-navy-700 rounded-xl bg-navy-800/30">
            <Database className="w-8 h-8 text-gray-700 mx-auto mb-3" />
            <p className="text-gray-500 text-sm">No reports yet.</p>
            <p className="text-gray-600 text-xs mt-1">{capabilities?.scraping ? 'Scrape or upload PDFs above to get started.' : 'Upload release note PDFs above to get started.'}</p>
          </div>
        )}

        <div className="space-y-2.5">
          {jobs?.map((job: Job) => <JobCard key={job.id} job={job} />)}
        </div>
      </section>
    </div>
  );
}

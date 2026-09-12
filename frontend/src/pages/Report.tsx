import {useTeam} from '../contexts/TeamContext';
import { groupContent, consolidationKeys } from "../utils/consolidation";
import { ConsolidationProvider, ConsolidateCheckbox, useConsolidation } from "../contexts/ConsolidationContext";
import PdfFileList from "../components/PdfFileList";
import PdfProcessingProgress from "../components/PdfProcessingProgress";
import { localDateTime } from "../utils/dateTime";
import ConfigAnalysis, { ConfigProvider, useConfigAnalysis } from "../config/ConfigAnalysis";
import { sourceRowId } from "../utils/sourceRowId";
import SourceContent from "../components/dashboard/SourceContent";
import { useMemo, useState, useCallback, useDeferredValue } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Loader2, XCircle, RefreshCw, Search, X, Printer, Trash2, FileDown } from "lucide-react";
import { api } from "../api";
import type { JobDetail, KnownIssue, TableItem, Feature } from "../types";
import TabNav from "../components/dashboard/TabNav";
import Overview from "../components/dashboard/Overview";
import SimpleTable from "../components/dashboard/SimpleTable";
import NewFeatures from "../components/dashboard/NewFeatures";
import FeatureDiff from "../components/dashboard/FeatureDiff";
import SpecialNotices from "../components/dashboard/SpecialNotices";
import KnownIssues from "../components/dashboard/KnownIssues";
import ExtendedSections from "../components/dashboard/ExtendedSections";
import PrintModal from "../components/dashboard/PrintModal";
import DownloadModal from "../components/dashboard/DownloadModal";
import type { ExtSlug } from "../components/dashboard/ExtendedSections";
import type { PrintItem } from "../components/dashboard/PrintModal";

// Keys rendered by dedicated tabs — excluded from dynamic More Sections discovery
const LEGACY_KEYS = new Set([
  "changes_cli", "changes_default", "changes_tablesize",
  "new_features", "known_issues",
  "resolved-issues", "resolved-issue",
  // Hyphenated variants of legacy slugs that extended scraper might emit
  "new-features-and-enhancements", "new-features-or-enhancements",
]);

function slugLabel(slug: string) {
  return slug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function isIssuesData(val: unknown): val is KnownIssue[] {
  return Array.isArray(val) && val.length > 0 && "Bug ID" in (val[0] as object);
}

// ── Search result item ────────────────────────────────────────────────────────
interface SearchItem {
  compositeId: string;
  compositeIds?: string[];
  section: string;
  sectionLabel: string;
  tabId: string;
  version: string;
  id: string;
  idLabel: string;
  category?: string;
  description: string;
  markdown?: string;
}

export default function Report() {
  const {id} = useParams();
  return <ConfigProvider key={id}><ConsolidationProvider><ReportContent /></ConsolidationProvider></ConfigProvider>;
}
function ReportContent() {
  const team=useTeam();const canExport=!team.enabled||team.permissions?.includes('reports.export');
  const {profile} = useConfigAnalysis();
  const {sections: consolidatedSections} = useConsolidation();
  const { id } = useParams<{ id: string }>();
  const [activeTab, setActiveTab] = useState<string>("overview");
  const [globalSel, setGlobalSel] = useState<Set<string>>(new Set());
  const [printOpen, setPrintOpen] = useState(false);
  const [downloadOpen, setDownloadOpen] = useState(false);
  const [globalSearch, setGlobalSearch] = useState("");
  const deferredSearch = useDeferredValue(globalSearch);

  const toggleGlobal = useCallback((itemId: string) => {
    setGlobalSel((prev) => {
      const next = new Set(prev);
      next.has(itemId) ? next.delete(itemId) : next.add(itemId);
      return next;
    });
  }, []);

  const clearGlobal = useCallback(() => setGlobalSel(new Set()), []);

  const { data: storedJob, isLoading, error, refetch } = useQuery({
    queryKey: ["job", id],
    queryFn: () => api.getJob(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === "pending" || s === "running" ? 3000 : false;
    },
  });

  const job = storedJob ? {...storedJob, localRelevance: profile, localConsolidation: consolidatedSections} : undefined;

  // ── All derived state and hooks must come before any early returns ──────────
  // (Rules of Hooks: hook call count must be identical on every render)
  const j = (job ?? {}) as JobDetail;
  const versions = j.versions ?? [];
  const allData  = j.all_data ?? {};

  function count(key: string) {
    return versions.reduce((s, v) => s + ((allData[v] as Record<string, unknown[]>)?.[key]?.length ?? 0), 0);
  }

  // ── Extended slugs (More Sections) ────────────────────────────────────────
  const extendedSlugs = useMemo<ExtSlug[]>(() => {
    const seen = new Map<string, { label: string; isIssues: boolean; totalCount: number }>();
    for (const ver of versions) {
      for (const [key, val] of Object.entries(allData[ver] ?? {})) {
        if (LEGACY_KEYS.has(key)) continue;
        if (key.startsWith("_")) continue;         // metadata keys like _section_urls
        if (!seen.has(key)) {
          seen.set(key, { label: !Array.isArray(val) && typeof val === "object" && val && "title" in val ? String(val.title) : slugLabel(key), isIssues: isIssuesData(val), totalCount: 0 });
        }
        if (isIssuesData(val)) {
          seen.get(key)!.totalCount += (val as KnownIssue[]).length;
        }
      }
    }
    return [...seen.entries()]
      .map(([slug, { label, isIssues, totalCount }]) => ({
        slug,
        label,
        isIssues,
        count: totalCount,
      }));
  }, [versions, allData]);

  // ── Source URLs for all sections ──────────────────────────────────────────
  const resolvedCount = count("resolved-issues") + count("resolved-issue");
  const resolvedKey   = count("resolved-issues") > 0 ? "resolved-issues" : "resolved-issue";

  /** Build a version→url map for a given section key from _section_urls */
  function buildSourceUrls(sectionKey: string): Record<string, string> | undefined {
    const urls: Record<string, string> = {};
    for (const ver of versions) {
      const secUrls = (allData[ver] as Record<string, unknown>)?._section_urls as Record<string, string> | undefined;
      if (secUrls?.[sectionKey]) urls[ver] = secUrls[sectionKey];
    }
    return Object.keys(urls).length > 0 ? urls : undefined;
  }

  const resolvedSourceUrls = useMemo(() => buildSourceUrls(resolvedKey),   [versions, allData, resolvedKey]);
  const cliSourceUrls      = useMemo(() => buildSourceUrls("changes_cli"),       [versions, allData]);
  const defaultSourceUrls  = useMemo(() => buildSourceUrls("changes_default"),   [versions, allData]);
  const tablesizeSourceUrls= useMemo(() => buildSourceUrls("changes_tablesize"),  [versions, allData]);
  const featuresSourceUrls = useMemo(() => buildSourceUrls("new_features"),       [versions, allData]);
  const issuesSourceUrls   = useMemo(() => buildSourceUrls("known_issues"),       [versions, allData]);

  // ── Global search index ───────────────────────────────────────────────────
  const allSearchItems = useMemo<SearchItem[]>(() => {
    const items: SearchItem[] = [];

    const issueSections: { key: string; label: string; tabId: string }[] = [
      { key: "known_issues",   label: "Known Issues",    tabId: "issues"   },
      { key: "resolved-issues", label: "Resolved Issues", tabId: "resolved" },
      { key: "resolved-issue",  label: "Resolved Issues", tabId: "resolved" },
    ];
    for (const { key, label, tabId } of issueSections) {
      for (const ver of versions) {
        for (const item of (allData[ver]?.[key] as KnownIssue[]) ?? []) {
          items.push({
            compositeId: sourceRowId(key, ver, item),
            section: key, sectionLabel: label, tabId, version: ver,
            id: item["Bug ID"], idLabel: "Bug ID",
            category: item.category, description: item.Description, markdown: item.markdown,
          });
        }
      }
    }

    const tableSections: { key: string; label: string; tabId: string }[] = [
      { key: "changes_cli",       label: "CLI Changes",      tabId: "cli"       },
      { key: "changes_default",   label: "Default Behavior", tabId: "default"   },
      { key: "changes_tablesize", label: "Table Size",        tabId: "tablesize" },
    ];
    for (const { key, label, tabId } of tableSections) {
      for (const ver of versions) {
        for (const item of (allData[ver]?.[key] as TableItem[]) ?? []) {
          items.push({
            compositeId: sourceRowId(key, ver, item),
            section: key, sectionLabel: label, tabId, version: ver,
            id: item["Bug ID"], idLabel: "Bug ID",
            description: item.Description, markdown: item.markdown,
          });
        }
      }
    }

    for (const ver of versions) {
      for (const item of (allData[ver]?.new_features as Feature[]) ?? []) {
        items.push({
          compositeId: sourceRowId("new_features", ver, item),
          section: "new_features", sectionLabel: "New Features", tabId: "features", version: ver,
          id: item["Feature ID"], idLabel: "Feature ID",
          category: item.category, description: item.Description, markdown: item.markdown,
        });
      }
    }

    // Extended issues sections
    for (const { slug, label } of extendedSlugs.filter((s) => s.isIssues)) {
      for (const ver of versions) {
        for (const item of (allData[ver]?.[slug] as KnownIssue[]) ?? []) {
          items.push({
            compositeId: sourceRowId(slug, ver, item),
            section: slug, sectionLabel: label, tabId: "more", version: ver,
            id: item["Bug ID"], idLabel: "Bug ID",
            category: item.category, description: item.Description, markdown: item.markdown,
          });
        }
      }
    }

    return items;
  }, [versions, allData, extendedSlugs]);

  function consolidateSearch(items: SearchItem[]): SearchItem[] {
    // Group within each source section. Never merge Known with Resolved issues.
    return groupContent(items, true, item => item.version, (item, index) =>
      consolidatedSections.includes(item.section)
        ? [item.section, item.idLabel, item.id, item.category, item.description, item.markdown]
        : [item.section, item.compositeId, index]
    ).map(group => ({...group.item, version: group.versions.join(', '),
      compositeIds: [...new Set(group.members.map(item => item.compositeId))]}));
  }
  const searchIds = (item: SearchItem) => item.compositeIds ?? [item.compositeId];
  const searchChecked = (item: SearchItem) => searchIds(item).every(id => globalSel.has(id));
  function toggleSearch(item: SearchItem) {
    const checked = searchChecked(item);
    searchIds(item).forEach(id => {if (globalSel.has(id) === checked) toggleGlobal(id);});
  }

  const searchResults = useMemo<SearchItem[]>(() => {
    if (!deferredSearch.trim()) return [];
    const q = deferredSearch.toLowerCase();
    return consolidateSearch(allSearchItems.filter(
      (item) =>
        item.id.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q) ||
        (item.category?.toLowerCase().includes(q) ?? false) ||
        item.sectionLabel.toLowerCase().includes(q) ||
        item.version.toLowerCase().includes(q)
    ));
  }, [allSearchItems, deferredSearch, consolidatedSections]);

  // ── Print data ────────────────────────────────────────────────────────────
  const printItems = useMemo<PrintItem[]>(() => {
    return consolidateSearch(allSearchItems
      .filter((item) => globalSel.has(item.compositeId)))
      .map((item) => ({
        compositeId: item.compositeId,
        sectionLabel: item.sectionLabel,
        version: item.version,
        id: item.id,
        idLabel: item.idLabel,
        category: item.category,
        description: item.description, markdown: item.markdown,
      }));
  }, [allSearchItems, globalSel, consolidatedSections]);

  // ── Tabs ──────────────────────────────────────────────────────────────────
  const tabs = [
    { id: "overview",  label: "Overview" },
    { id: "cli",       label: "CLI Changes",      count: count("changes_cli") },
    { id: "default",   label: "Default Behavior", count: count("changes_default") },
    { id: "tablesize", label: "Table Size",        count: count("changes_tablesize") },
    { id: "features",  label: "New Features",      count: count("new_features") },
    { id: "diff",      label: "Feature Diff" },
    { id: "notices",   label: "Special Notices",   count: j.special_notices?.length },
    { id: "issues",    label: "Known Issues",      count: count("known_issues") },
    ...(resolvedCount > 0
      ? [{ id: "resolved", label: "Resolved Issues", count: resolvedCount }]
      : []),
    ...(extendedSlugs.length > 0
      ? [{ id: "more", label: "More Sections", count: extendedSlugs.length }]
      : []),
  ];

  // Section badge colours for search results
  const SECTION_COLORS: Record<string, string> = {
    "Known Issues":    "bg-red-900/40 text-red-300",
    "Resolved Issues": "bg-orange-900/40 text-orange-300",
    "CLI Changes":     "bg-sky-900/40 text-sky-300",
    "Default Behavior":"bg-amber-900/40 text-amber-300",
    "Table Size":      "bg-violet-900/40 text-violet-300",
    "New Features":    "bg-emerald-900/40 text-emerald-300",
  };

  // ── Early returns — all hooks are called above ────────────────────────────
  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-3 py-32 text-gray-400">
        <Loader2 className="w-5 h-5 animate-spin" />
        Loading report…
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="max-w-xl mx-auto py-24 text-center">
        <XCircle className="w-10 h-10 text-red-400 mx-auto mb-4" />
        <p className="text-red-300 mb-6">{(error as Error)?.message ?? "Report not found"}</p>
        <Link to="/" className="text-brand-500 hover:underline text-sm">← Back to home</Link>
      </div>
    );
  }

  if (!["completed", "partial"].includes(job.status)) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-12 space-y-6">
        <Link to="/library" className="flex items-center gap-1.5 text-gray-400 hover:text-white text-sm transition-colors">
          <ArrowLeft className="w-4 h-4" /> All reports
        </Link>
        <div className="bg-navy-800 border border-navy-700 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-4">
            {job.status === "running" && <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />}
            {job.status === "failed"  && <XCircle className="w-5 h-5 text-red-400" />}
            <span className="text-white font-semibold">
              {job.from_version} → {job.to_version}
            </span>
            <span className="text-sm text-gray-400 capitalize">{job.status}</span>
          </div>
          <PdfProcessingProgress job={job} />
          <PdfFileList files={job.file_outcomes} jobStatus={job.status} />
          {job.error_message && (
            <p className="text-red-300 text-sm bg-red-900/20 border border-red-800/30 rounded-lg px-4 py-3 mb-4">
              {job.error_message}
            </p>
          )}
          {job.log && (
            <pre className="text-xs font-mono text-gray-400 bg-gray-950 border border-gray-800 rounded-lg px-4 py-3 max-h-72 overflow-y-auto whitespace-pre-wrap">
              {job.log.trim()}
            </pre>
          )}
          {job.status === "failed" && (
            <button onClick={() => refetch()} className="mt-4 flex items-center gap-2 text-sm text-gray-400 hover:text-white">
              <RefreshCw className="w-4 h-4" /> Refresh
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-screen-2xl mx-auto px-6 py-6 space-y-5 pb-24">
      {/* Back + title */}
      <div className="flex flex-wrap items-center gap-4">
        <Link to="/library" className="flex items-center gap-1.5 text-gray-400 hover:text-white text-sm transition-colors">
          <ArrowLeft className="w-4 h-4" /> All reports
        </Link>
        <h1 className="text-white font-semibold text-lg">
          {j.title || "Upgrade report"}:{" "}
          <span className="font-mono text-brand-500">{j.from_version}</span>
          <span className="text-gray-500 mx-2">→</span>
          <span className="font-mono text-brand-500">{j.to_version}</span>
        </h1>
        <span className="text-xs text-gray-500 ml-auto">
          {versions.length} version{versions.length !== 1 ? "s" : ""}
          {j.completed_at && ` · generated ${localDateTime(j.completed_at)}`}
        </span>
        <button
          disabled={!canExport} onClick={() => setDownloadOpen(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-300 hover:text-white bg-navy-800 hover:bg-navy-700 border border-navy-700 rounded-lg transition-colors shrink-0"
          title="Download self-contained HTML report"
        >
          <FileDown className="w-3.5 h-3.5" />
          Download HTML
        </button>
      </div>

      {job.source === 'pdf' && <details className="rounded-lg border border-navy-600 p-4"><summary className="text-sm font-semibold text-white cursor-pointer">PDF documents · pages and processing times</summary><PdfFileList files={job.file_outcomes} jobStatus={job.status} /></details>}

      {/* Global search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
        <input
          type="text"
          value={globalSearch}
          onChange={(e) => setGlobalSearch(e.target.value)}
          placeholder="Search across all sections and versions…"
          className="w-full bg-gray-900 border border-gray-700 rounded-lg pl-9 pr-9 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-500 transition-colors"
        />
        {globalSearch && (
          <button
            onClick={() => setGlobalSearch("")}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Tab navigation (hidden while searching) */}
      <section className="text-sm space-y-1 my-3" aria-label="Report provenance">
          <p>Source: {j.source ?? 'legacy'} · Imported: {localDateTime(j.created_at)} · Status: {j.status} · Parser: {j.provenance?.parser_revision ?? 'legacy / not recorded'}</p>
          <p>Document revision: {j.provenance?.document_revision ?? 'See source change log.'}</p>
          <p>Missing sections mean not captured or not present in this source, not necessarily no changes.</p>
          <details><summary>Section completeness by version</summary>{versions.map(v => {
            const states = allData[v]?._section_status as Record<string, string> | undefined;
            return <div key={v}><strong>{v}</strong>{states ? <ul>{Object.entries(states).map(([section, state]) => <li key={section}>{section.replace(/[-_]/g, ' ')}: {state === 'not_captured' ? 'not captured / not found' : state === 'captured_empty' ? 'captured, no rows' : 'captured'}</li>)}</ul> : <p>Legacy report: section completeness was not recorded.</p>}</div>;
          })}</details>
          {j.warnings?.map(w => <p role="alert" key={w}>{w}</p>)}
        </section>
        <ConfigAnalysis />
      {!globalSearch && (
      <TabNav tabs={tabs} active={activeTab} onChange={setActiveTab} />
      )}

      {/* Tab content / search results */}
      <div className="py-3 space-y-1">
        <ConsolidateCheckbox allSections={consolidationKeys(j)} />
        <p className="text-xs text-gray-500">Matching entries appear once with the builds they occur in. Changed text or formatting stays separate.</p>
      </div>
      <div className="pt-2">
        {globalSearch ? (
          /* ── Search results ── */
          <div className={`space-y-3 transition-opacity duration-150 ${deferredSearch !== globalSearch ? "opacity-60" : "opacity-100"}`}>
            <div className="flex items-center justify-between text-xs text-gray-500">
              <span>
                {searchResults.length} result{searchResults.length !== 1 ? "s" : ""} for{" "}
                <span className="text-white">"{globalSearch}"</span>
              </span>
              {searchResults.length > 0 && (
                <button
                  onClick={() => {
                    new Set(searchResults.flatMap(searchIds)).forEach(id => {
                      if (!globalSel.has(id)) toggleGlobal(id);
                    });
                  }}
                  className="text-brand-400 hover:text-brand-300 transition-colors"
                >
                  Select all results
                </button>
              )}
            </div>

            {searchResults.length === 0 ? (
              <div className="text-center text-gray-600 py-16 text-sm">No results found.</div>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-gray-800">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="bg-gray-900 border-b border-gray-800">
                      <th className="py-2.5 px-3 w-8">
                        <input
                          type="checkbox"
                          checked={searchResults.every(searchChecked)}
                          onChange={() => {
                            const allChecked = searchResults.every(searchChecked);
                            new Set(searchResults.flatMap(searchIds)).forEach(id => {
                              if (allChecked === globalSel.has(id)) toggleGlobal(id);
                            });
                          }}
                          className="accent-brand-500 cursor-pointer"
                        />
                      </th>
                      <th className="text-left text-xs font-medium py-2.5 px-4 w-36">Section</th>
                      <th className="text-left text-xs font-medium py-2.5 px-4 w-20">Builds</th>
                      <th className="text-left text-xs font-medium py-2.5 px-4 w-28">ID</th>
                      <th className="text-left text-xs font-medium py-2.5 px-4 w-36">Category</th>
                      <th className="text-left text-xs font-medium py-2.5 px-4">Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {searchResults.map((item, index) => {
                      const checked = searchChecked(item);
                      return (
                        <tr
                          key={`${item.compositeId}:${index}`}
                          onClick={() => toggleSearch(item)}
                          className={`border-b border-gray-800/50 cursor-pointer transition-colors ${
                            checked ? "bg-brand-500/10" : "hover:bg-gray-900/30"
                          }`}
                        >
                          <td className="py-2.5 px-3 text-center" onClick={(e) => e.stopPropagation()}>
                            <input
                              type="checkbox"
                              checked={checked}
                              ref={el => {if (el) el.indeterminate = !checked && searchIds(item).some(id => globalSel.has(id));}}
                              onChange={() => toggleSearch(item)}
                              className="accent-brand-500 cursor-pointer"
                            />
                          </td>
                          <td className="py-2.5 px-4">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setActiveTab(item.tabId);
                                setGlobalSearch("");
                              }}
                              className={`text-xs px-2 py-0.5 rounded-full font-medium transition-colors hover:opacity-80 ${
                                SECTION_COLORS[item.sectionLabel] ?? "bg-gray-800 text-gray-300"
                              }`}
                            >
                              {item.sectionLabel}
                            </button>
                          </td>
                          <td className="py-2.5 px-4 font-mono text-xs text-gray-400 min-w-24">{item.version}</td>
                          <td className="py-2.5 px-4 font-mono text-xs text-red-400 whitespace-nowrap">{item.id}</td>
                          <td className="py-2.5 px-4 text-xs text-amber-400">{item.category ?? "—"}</td>
                          <td className="py-2.5 px-4 text-xs text-gray-300 leading-relaxed"><SourceContent markdown={item.markdown} text={item.description} /></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : (
          /* ── Tab content ── */
          <>
            {activeTab === "overview"  && <Overview job={j} />}
            {activeTab === "cli"       && <SimpleTable job={j} sectionKey="changes_cli"       idLabel="Bug ID" sourceUrls={cliSourceUrls}       globalSel={globalSel} onGlobalToggle={toggleGlobal} />}
            {activeTab === "default"   && <SimpleTable job={j} sectionKey="changes_default"   idLabel="Bug ID" sourceUrls={defaultSourceUrls}   globalSel={globalSel} onGlobalToggle={toggleGlobal} />}
            {activeTab === "tablesize" && <SimpleTable job={j} sectionKey="changes_tablesize" idLabel="Bug ID" sourceUrls={tablesizeSourceUrls} globalSel={globalSel} onGlobalToggle={toggleGlobal} />}
            {activeTab === "features"  && <NewFeatures job={j} sourceUrls={featuresSourceUrls} />}
            {activeTab === "diff"      && <FeatureDiff job={j} />}
            {activeTab === "notices"   && <SpecialNotices job={j} />}
            {activeTab === "issues"    && <KnownIssues job={j} sourceUrls={issuesSourceUrls} globalSel={globalSel} onGlobalToggle={toggleGlobal} />}
            {activeTab === "resolved"  && <KnownIssues job={j} dataKey={resolvedKey} sourceUrls={resolvedSourceUrls} globalSel={globalSel} onGlobalToggle={toggleGlobal} />}
            {activeTab === "more"      && <ExtendedSections job={j} slugs={extendedSlugs} globalSel={globalSel} onGlobalToggle={toggleGlobal} />}
          </>
        )}
      </div>

      {/* Sticky selection footer */}
      {globalSel.size > 0 && (
        <div className="fixed bottom-0 left-0 right-0 z-40 bg-navy-800/95 backdrop-blur border-t border-navy-600 px-6 py-3 flex items-center gap-4">
          <span className="text-white text-sm font-medium">
            {globalSel.size} item{globalSel.size !== 1 ? "s" : ""} selected
          </span>
          <span className="text-gray-500 text-xs">across {new Set(printItems.map((i) => i.sectionLabel)).size} section{new Set(printItems.map((i) => i.sectionLabel)).size !== 1 ? "s" : ""}</span>
          <div className="ml-auto flex items-center gap-3">
            <button
              disabled={!canExport} onClick={() => setPrintOpen(true)}
              className="flex items-center gap-2 px-4 py-1.5 bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium rounded-lg transition-colors"
            >
              <Printer className="w-3.5 h-3.5" />
              Print / Preview
            </button>
            <button
              onClick={clearGlobal}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-400 hover:text-white transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Clear all
            </button>
          </div>
        </div>
      )}

      {/* Print modal */}
      {printOpen && (
        <PrintModal items={printItems} onClose={() => setPrintOpen(false)} />
      )}

      {/* Download HTML modal */}
      {downloadOpen && (
        <DownloadModal job={j} onClose={() => setDownloadOpen(false)} />
      )}
    </div>
  );
}

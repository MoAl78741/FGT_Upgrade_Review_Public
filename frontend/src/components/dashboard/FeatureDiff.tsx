import {compareFeatures} from "../../utils/featureComparison";
import SourceContent from "./SourceContent";
import { useState, useMemo } from "react";
import type { JobDetail, Feature } from "../../types";

interface Props {
  job: JobDetail;
}

export default function FeatureDiff({ job }: Props) {
  const versions = job.versions ?? [];
  const allData  = job.all_data ?? {};

  const [verA, setVerA] = useState(versions[0] ?? "");
  const [verB, setVerB] = useState(versions[versions.length - 1] ?? "");

  const featA = useMemo<Feature[]>(
    () => allData[verA]?.new_features ?? [],
    [allData, verA]
  );
  const featB = useMemo<Feature[]>(
    () => allData[verB]?.new_features ?? [],
    [allData, verB]
  );

  const {onlyA, onlyB, shared, changed} = compareFeatures(featA, featB);

  if (versions.length < 2) {
    return (
      <p className="text-gray-500 text-sm py-12 text-center">
        Need at least two versions to compare.
      </p>
    );
  }

  const selectClass =
    "bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500 transition-colors";

  return (
    <div className="space-y-6">
      <p className="text-sm">Release-note differences describe these documents. Absence from a release note does not prove a feature was removed.</p>
      {changed.size > 0 && <section><h3 className="font-semibold">Changed descriptions ({changed.size} shared IDs)</h3><div className="grid md:grid-cols-2 gap-4"><DiffColumn title={`Version ${verA}`} items={featA.filter(f => changed.has(f['Feature ID']))} color="text-sky-400" /><DiffColumn title={`Version ${verB}`} items={featB.filter(f => changed.has(f['Feature ID']))} color="text-emerald-400" /></div></section>}
      {/* Version pickers */}
      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm text-gray-400">
          Version A:
          <select value={verA} onChange={(e) => setVerA(e.target.value)} className={selectClass}>
            {versions.map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-400">
          Version B:
          <select value={verB} onChange={(e) => setVerB(e.target.value)} className={selectClass}>
            {versions.map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        </label>
      </div>

      {/* Summary badges */}
      <div className="flex gap-4 text-sm">
        <span className="px-3 py-1.5 rounded-lg bg-sky-900/30 text-sky-300 border border-sky-800/30">
          {onlyA.length} only in v{verA}
        </span>
        <span className="px-3 py-1.5 rounded-lg bg-emerald-900/30 text-emerald-300 border border-emerald-800/30">
          {onlyB.length} only in v{verB}
        </span>
        <span className="px-3 py-1.5 rounded-lg bg-gray-800 text-gray-400 border border-gray-700">
          {shared.length} shared
        </span>
      </div>

      {/* Side-by-side columns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <DiffColumn title={`Only in v${verA}`} items={onlyA} color="text-sky-400" />
        <DiffColumn title={`Only in v${verB}`} items={onlyB} color="text-emerald-400" />
      </div>

      {shared.length > 0 && (
        <div>
          <h3 className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-3">
            Shared ({shared.length})
          </h3>
          <DiffColumn title="" items={shared} color="text-gray-400" />
        </div>
      )}
    </div>
  );
}

function DiffColumn({
  title,
  items,
  color,
}: {
  title: string;
  items: Feature[];
  color: string;
}) {
  return (
    <div>
      {title && (
        <h3 className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-3">{title}</h3>
      )}
      {items.length === 0 ? (
        <p className="text-gray-600 text-sm py-6 text-center border border-dashed border-gray-800 rounded-xl">
          None
        </p>
      ) : (
        <div className="rounded-xl border border-gray-800 overflow-hidden">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="bg-gray-900 border-b border-gray-800">
                <th className="text-left text-gray-500 font-medium py-2 px-3 w-28">Feature ID</th>
                <th className="text-left text-gray-500 font-medium py-2 px-3 w-32">Category</th>
                <th className="text-left text-gray-500 font-medium py-2 px-3">Description</th>
              </tr>
            </thead>
            <tbody>
              {items.map((f, i) => (
                <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-900/30 transition-colors">
                  <td className={`py-2 px-3 font-mono whitespace-nowrap ${color}`}>{f["Feature ID"]}</td>
                  <td className="py-2 px-3 text-gray-400">{f.category}</td>
                  <td className="py-2 px-3 text-gray-300 leading-relaxed"><SourceContent text={f.Description} markdown={f.markdown} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

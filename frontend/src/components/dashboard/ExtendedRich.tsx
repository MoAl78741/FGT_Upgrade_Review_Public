import SectionContent,{type SectionValue} from './SectionContent';
import { richGroups } from "../../utils/consolidation";
import { ConsolidateCheckbox, useConsolidation } from "../../contexts/ConsolidationContext";
import { useState, useEffect } from "react";
import { ExternalLink } from "lucide-react";
import type { JobDetail } from "../../types";


interface Props {
  job: JobDetail;
  slugKey: string;
}

export default function ExtendedRich({ job, slugKey }: Props) {
  const {sections} = useConsolidation();
  const consolidate = sections.includes(slugKey);
  const versions = (job.versions ?? []).filter((v) => {
    const d = (job.all_data?.[v] as Record<string, unknown> | undefined)?.[slugKey];
    const s = d as SectionValue | undefined;
    return !!(s && (Array.isArray(s) ? s.length : s.markdown || s.blocks?.length));
  });

  const [selected, setSelected] = useState<string>(versions[0] ?? "");

  // When the section changes (slugKey prop), reset to the first available version
  useEffect(() => {
    setSelected(versions[0] ?? "");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slugKey]);

  if (versions.length === 0) {
    return (
      <div className="text-center text-gray-600 py-12 text-sm">
        No content available for this section.
      </div>
    );
  }

  if (consolidate) return <div className="space-y-4">
    <ConsolidateCheckbox section={slugKey} />
    {richGroups(job, slugKey, true).map(({item: {section}, versions: builds}, i) =>
      <div key={i} className="bg-navy-800 border border-navy-700 rounded-xl px-6 py-5">
        <p className="text-sm font-mono text-gray-400 mb-3">Builds: {builds.join(', ')}</p>
        <SectionContent value={section} />
      </div>)}
  </div>;

  const versionData = (job.all_data?.[selected] as Record<string, unknown> | undefined);
  const section = versionData?.[slugKey] as SectionValue | undefined;
  const sourceUrl = (versionData?._section_urls as Record<string, string> | undefined)?.[slugKey];

  return (
    <div className="space-y-4">
      <ConsolidateCheckbox section={slugKey} />
      {/* Version selector + source link */}
      {(versions.length > 1 || sourceUrl) && (
        <div className="flex flex-wrap items-center gap-2">
          {versions.map((v) => (
            <button
              key={v}
              onClick={() => setSelected(v)}
              className={`px-3 py-1 rounded-lg text-xs font-mono font-medium transition-colors ${
                selected === v
                  ? "bg-brand-500 text-white"
                  : "bg-gray-800 text-gray-400 hover:text-gray-200"
              }`}
            >
              {v}
            </button>
          ))}
          {sourceUrl && (
            <a
              href={sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-auto flex items-center gap-1 text-xs text-gray-500 hover:text-brand-400 transition-colors"
            >
              <ExternalLink className="w-3 h-3" />
              View in Docs
            </a>
          )}
        </div>
      )}

      {/* Content */}
      {section ? (
        <div className="bg-navy-800 border border-navy-700 rounded-xl px-6 py-5"><SectionContent value={section}/></div>
      ) : (
        <div className="text-center text-gray-600 py-12 text-sm">
          No content for v{selected}.
        </div>
      )}
    </div>
  );
}

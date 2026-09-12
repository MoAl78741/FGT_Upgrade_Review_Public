import { groupNotices } from "../../utils/consolidation";
import { ConsolidateCheckbox, useConsolidation } from "../../contexts/ConsolidationContext";
import { AlertTriangle } from "lucide-react";
import SourceContent, { SourceBlocks } from "./SourceContent";
import type { JobDetail } from "../../types";


interface Props {
  job: JobDetail;
}

export default function SpecialNotices({ job }: Props) {
  const {sections} = useConsolidation();
  const consolidate = sections.includes("special_notices");
  const notices = groupNotices(job.special_notices ?? [], consolidate);

  if (notices.length === 0) {
    return (
      <p className="text-gray-500 text-sm py-12 text-center">
        No special notices found for v{job.to_version}.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <ConsolidateCheckbox section="special_notices" />
      {notices.map(({item: notice, versions}, i) => (
        <div
          key={i}
          className="bg-amber-900/20 border border-amber-700/40 rounded-xl p-5"
        >
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
            <div>
              {notice.version && <p className="text-sm text-gray-400 mb-1">{consolidate ? "Builds: " : "FortiOS "}{versions.join(", ")}</p>}
              {notice.title && (
                <h3 className="text-amber-400 font-semibold text-sm mb-2">{notice.title}</h3>
              )}
              {notice.markdown ? (
                /* PDF source: render extracted markdown (searchable, selectable) */
                <div className="mt-1">
                  <SourceContent markdown={notice.markdown} />
                </div>
              ) : notice.blocks?.length ? (
                <SourceBlocks blocks={notice.blocks} />
              ) : (
                <p className="text-gray-300 text-sm leading-relaxed whitespace-pre-line">
                  {notice.content}
                </p>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

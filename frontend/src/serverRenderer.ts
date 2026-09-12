// A trusted, pure renderer shared with the browser. No config inputs are accepted by HTTP routes.
import {reportView, reportHtml, reportDelimited} from './utils/reportApi';
import {compareFeatures} from './utils/featureComparison';
import {pdfReleaseRange, pdfCatalog} from './utils/pdfReleaseRange';
import {reviewPackageHtml} from './utils/reviewExport';
import type {JobDetail} from './types';
export function render(input: any) {
  const {job, options = {}, operation} = input;
  if (operation === 'releases') return input.from ? {...pdfCatalog, releases: pdfReleaseRange(input.from,input.to,input.include_from)} : pdfCatalog;
  if (operation === 'review') return reviewPackageHtml(input.review);
  if (operation === 'html') return reportHtml(job, options);
  if (operation === 'csv' || operation === 'txt') return reportDelimited(job, options, operation === 'txt' ? '\t' : ',');
  if (operation === 'compare') {
    const data = (job as JobDetail).all_data ?? {};
    const result = compareFeatures(data[input.from]?.new_features ?? [], data[input.to]?.new_features ?? []);
    return {...result, changed: [...result.changed], from_version: input.from, to_version: input.to,
      interpretation: 'Release-note differences only; absence is not evidence of a removed product feature.'};
  }
  const result = reportView(job, options);
  return {...result, entries: result.entries.slice(input.offset ?? 0, (input.offset ?? 0) + (input.limit ?? result.count))};
}

import type {JobDetail,KnownIssue} from '../types';
/** Display-only compatibility: retain every occurrence; never alter stored JSON. */
export function resolvedDisplayJob(job:JobDetail):JobDetail {
 if(!Object.values(job.all_data||{}).some(data=>Array.isArray(data['resolved-issue'])))return job;
 return {...job,all_data:Object.fromEntries(Object.entries(job.all_data||{}).map(([version,data])=>{
  const legacy=data['resolved-issue'];if(!Array.isArray(legacy))return [version,data];
  const {'resolved-issue':_,...copy}=data;
  copy['resolved-issues']=[...legacy,...(Array.isArray(data['resolved-issues'])?data['resolved-issues']:[])] as KnownIssue[];
  const urls=data._section_urls;if(urls)copy._section_urls={...urls,'resolved-issues':urls['resolved-issues']||urls['resolved-issue']};
  return [version,copy];
 })),localConsolidation:job.localConsolidation?.includes('resolved-issue')?[...new Set([...job.localConsolidation,'resolved-issues'])]:job.localConsolidation};
}

import SourceContent,{SourceBlocks} from './SourceContent';
import type {RichSection,RichBlock} from '../../types';
export type SectionValue=RichSection|Record<string,unknown>[];
/** Shared fallback for structured chapters and non-issue row sections. */
export default function SectionContent({value}:{value:SectionValue}){
 if(Array.isArray(value))return <>{value.map((row,i)=><article key={i} className="source-section-entry">
  {!!(row['Bug ID']||row['Feature ID']||row.category||row.title)&&<p>{[row['Bug ID']||row['Feature ID'],row.category,row.title].filter(Boolean).map(String).join(' · ')}</p>}
  {Array.isArray(row.blocks)&&!row.markdown?<SourceBlocks blocks={row.blocks as RichBlock[]}/>:<SourceContent markdown={typeof row.markdown==='string'?row.markdown:undefined} text={String(row.Description??row.description??row.content??row.text??'')}/>}
 </article>)}</>;
 return value.markdown?<SourceContent markdown={value.markdown}/>:<SourceBlocks blocks={value.blocks||[]}/>;
}

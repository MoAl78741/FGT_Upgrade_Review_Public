import SourceContent, {SourceBlocks} from './dashboard/SourceContent';
import type { Finding } from '../reviews';

export default function ReviewSource({source}: {source: Finding['source']}) {
  return source.markdown ? <SourceContent markdown={source.markdown} /> : source.blocks?.length ? <SourceBlocks blocks={source.blocks} /> : <SourceContent text={source.Description || source.description || source.content || ''} />;
}

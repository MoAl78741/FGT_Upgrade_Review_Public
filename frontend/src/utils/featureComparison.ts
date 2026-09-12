import type {Feature} from '../types';
/** Compare document variants, never infer runtime product feature removal. */
export function compareFeatures(featA: Feature[], featB: Feature[]) {
  const idsA = new Set(featA.map(f => f['Feature ID']));
  const idsB = new Set(featB.map(f => f['Feature ID']));
  const signature = (f: Feature) => JSON.stringify([f.category, f.Description, f.markdown ?? '']);
  const variants = (items: Feature[], id: string) => items.filter(f => f['Feature ID'] === id).map(signature).sort().join('\n');
  const changed = new Set(featA.filter(f => idsB.has(f['Feature ID']) && variants(featA, f['Feature ID']) !== variants(featB, f['Feature ID'])).map(f => f['Feature ID']));
  return {
    onlyA: featA.filter(f => !idsB.has(f['Feature ID'])),
    onlyB: featB.filter(f => !idsA.has(f['Feature ID'])),
    shared: featA.filter(f => idsB.has(f['Feature ID']) && !changed.has(f['Feature ID'])),
    changed, changedA: featA.filter(f => changed.has(f['Feature ID'])), changedB: featB.filter(f => changed.has(f['Feature ID'])),
  };
}

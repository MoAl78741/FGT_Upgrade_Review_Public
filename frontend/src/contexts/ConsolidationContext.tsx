import { createContext, useContext, useState, type ReactNode } from 'react';
const Context = createContext({sections: [] as string[], setSections: (_: string[]) => {}});
export function ConsolidationProvider({children}: {children: ReactNode}) {
  const [sections, setSections] = useState<string[]>([]);
  return <Context.Provider value={{sections, setSections}}>{children}</Context.Provider>;
}
export const useConsolidation = () => useContext(Context);
export function ConsolidateCheckbox({section, allSections}: {section?: string; allSections?: string[]}) {
  const {sections, setSections} = useConsolidation();
  const keys = allSections ?? (section ? [section] : []);
  const checked = keys.length > 0 && keys.every(k => sections.includes(k));
  const partial = !checked && keys.some(k => sections.includes(k));
  return <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
    <input type="checkbox" className="accent-brand-500" checked={checked}
      ref={el => {if (el) el.indeterminate = partial;}}
      onChange={e => setSections(e.target.checked ? [...new Set([...sections, ...keys])] : sections.filter(k => !keys.includes(k)))} />
    {allSections ? 'Consolidate duplicates in all sections' : 'Consolidate duplicates'}
  </label>;
}

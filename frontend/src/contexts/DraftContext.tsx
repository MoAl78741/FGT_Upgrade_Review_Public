import {createContext,useContext,useEffect,useId,useState,type ReactNode} from 'react';
import {useBlocker} from 'react-router-dom';
const Context=createContext({dirty:false,setDirty:(_id:string,_dirty:boolean)=>{},confirmDiscard:():boolean=>true});
export function DraftProvider({children}:{children:ReactNode}){
 const [entries,setEntries]=useState<Record<string,boolean>>({});const dirty=Object.values(entries).some(Boolean);
 const [setDirty]=useState(()=>(id:string,value:boolean)=>setEntries(old=>{if(old[id]===value)return old;const next={...old};if(value)next[id]=true;else delete next[id];return next}));
 const blocker=useBlocker(dirty);
 useEffect(()=>{if(blocker.state==='blocked'){if(window.confirm('Leave this page and discard unsaved edits?'))blocker.proceed();else blocker.reset();}},[blocker]);
 useEffect(()=>{if(!dirty)return;const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue=''};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[dirty]);
 return <Context.Provider value={{dirty,setDirty,confirmDiscard:()=>!dirty||window.confirm('This action may discard unsaved finding edits. Continue?')}}>{children}</Context.Provider>
}
export const useDrafts=()=>useContext(Context);
export function useDraft(value:unknown){const id=useId(),{setDirty}=useDrafts();const json=JSON.stringify(value);const [saved,setSaved]=useState(json);const dirty=json!==saved;useEffect(()=>{setDirty(id,dirty);return()=>setDirty(id,false)},[id,dirty,setDirty]);return {dirty,markSaved:()=>setSaved(json)}}

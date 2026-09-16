// Bounded, uncompressed ZIP writer. No scripts, configuration profiles or secrets are added.
export type ArchiveEntry={name:string;data:Uint8Array};
export const ARCHIVE_LIMIT=256*1024**2;
export function sessionZip(entries:ArchiveEntry[]):Blob{
 const crcTable=Array.from({length:256},(_,i)=>{let c=i;for(let j=0;j<8;j++)c=(c>>>1)^((c&1)?0xedb88320:0);return c>>>0});
 const enc=new TextEncoder(),chunks:Uint8Array[]=[],central:Uint8Array[]=[];let offset=0,total=0;
 if(entries.length>2000)throw Error('Too many archive entries. Download reports individually.');
 for(const e of entries){total+=e.data.length;if(total>ARCHIVE_LIMIT)throw Error('Archive exceeds 256 MiB. Download reports individually.');if(!/^[a-zA-Z0-9_./-]+$/.test(e.name)||e.name.startsWith('/')||e.name.split('/').includes('..'))throw Error('Invalid archive name');const name=enc.encode(e.name);let crc=0xffffffff;for(const byte of e.data)crc=(crc>>>8)^crcTable[(crc^byte)&255];crc=(crc^0xffffffff)>>>0;
 const header=new Uint8Array(30+name.length),h=new DataView(header.buffer);h.setUint32(0,0x04034b50,true);h.setUint16(4,20,true);h.setUint16(6,0x800,true);h.setUint32(14,crc,true);h.setUint32(18,e.data.length,true);h.setUint32(22,e.data.length,true);h.setUint16(26,name.length,true);header.set(name,30);
 const c=new Uint8Array(46+name.length),v=new DataView(c.buffer);v.setUint32(0,0x02014b50,true);v.setUint16(4,20,true);v.setUint16(6,20,true);v.setUint16(8,0x800,true);v.setUint32(16,crc,true);v.setUint32(20,e.data.length,true);v.setUint32(24,e.data.length,true);v.setUint16(28,name.length,true);v.setUint32(42,offset,true);c.set(name,46);central.push(c);chunks.push(header,e.data);offset+=header.length+e.data.length;
 }
 const size=central.reduce((n,x)=>n+x.length,0),end=new Uint8Array(22),v=new DataView(end.buffer);v.setUint32(0,0x06054b50,true);v.setUint16(8,entries.length,true);v.setUint16(10,entries.length,true);v.setUint32(12,size,true);v.setUint32(16,offset,true);
 return new Blob([...chunks,...central,end].map(x=>Uint8Array.from(x).buffer),{type:'application/zip'});
}
export function saveDownload(blob:Blob,name:string){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000)}

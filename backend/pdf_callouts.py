"""Recognize bordered PDF note regions without interpreting their severity."""
import re
from .pdf_issue_markdown import _page_lines, _normalized, _markdown


def _text(block):
    if block.get('type')=='list':return ' '.join(block.get('items',[]))
    return block.get('text','')


def add_callouts(pdf_path,data,notices,section_pages,notice_pages):
    from .pdf_document import open_document, Rect
    cache={}
    with open_document(pdf_path) as doc:
        def regions(number):
            if number in cache:return cache[number]
            page=doc[number]
            images=[Rect(image['bbox']) for image in page.get_image_info()]
            images=[rect for rect in images if 10<rect.width<70 and 10<rect.height<90 and rect.x0<page.rect.width/3 and rect.y0>65]
            if not images:
                cache[number]=[];return []
            rules=[d['rect'] for d in page.get_drawings() if d['rect'].height<1 and d['rect'].width>page.rect.width/2]
            lines=_page_lines(page,number);found=[]
            for rect in images:
                above=[r for r in rules if r.y0<=rect.y0 and r.x0<=rect.x0 and r.x1>=rect.x1]
                below=[r for r in rules if r.y0>=rect.y1 and r.x0<=rect.x0 and r.x1>=rect.x1]
                if not above or not below:continue
                top=max(above,key=lambda r:r.y0);bottom=min(below,key=lambda r:r.y0)
                if bottom.y0-top.y0>240 or abs(top.x0-bottom.x0)>2 or abs(top.x1-bottom.x1)>2:continue
                selected=[line for line in lines if rect.x1<line['x']<top.x1 and top.y0<line['y']<bottom.y0]
                if selected:
                    text=' '.join(line['text'] for line in selected)
                    found.append((text,'\n'.join('> '+line for line in _markdown(selected).splitlines()),top.y0))
            cache[number]=found;return found
        entries=[(section,section_pages.get(key,[])) for key,section in data.items() if isinstance(section,dict) and 'blocks' in section]
        entries += [(notice,notice_pages.get(notice.get('title',''),[])) for notice in notices]
        for section,pages in entries:
            for number in pages:
                for text,markdown,_ in regions(number):
                    wanted=_normalized(text);blocks=section.get('blocks',[])
                    for start in range(len(blocks)):
                        collected=''
                        for end in range(start,len(blocks)):
                            if blocks[end].get('type') not in {'paragraph','list','code'}:break
                            collected+=_normalized(_text(blocks[end]))
                            if collected==wanted:
                                blocks[start:end+1]=[{'type':'paragraph','text':text,'markdown':markdown,'source_note':True}]
                                section.pop('markdown',None)
                                break
                            if not wanted.startswith(collected):break
                        else:continue
                        if collected==wanted:break
        by_id={}
        for rows in data.values():
            if not isinstance(rows,list):continue
            for row in rows:
                if not isinstance(row,dict) or not row.get('markdown') or not row.get('Description'):continue
                identifier=_normalized(row.get('Bug ID',row.get('Feature ID','')))
                if identifier:by_id.setdefault(identifier,[]).append(row)
        anchors={}
        def page_ids(number):
            if number not in anchors:
                anchors[number]=[(line['y'],_normalized(line['text'])) for line in _page_lines(doc[number],number)
                                 if line['x']<120 and _normalized(line['text']) in by_id]
            return sorted(anchors[number])
        for number in range(len(doc)):
            for text,quoted,top in regions(number):
                before=[item for item in page_ids(number) if item[0]<top]
                if not before and number:before=page_ids(number-1)
                if not before:continue
                needle='\n'.join(line[2:] if line.startswith('> ') else line for line in quoted.splitlines())
                for row in by_id.get(before[-1][1],[]):
                    if _normalized(text) not in _normalized(row['Description']):continue
                    pattern=r'(?m)(?:\A|(?<=\n\n))'+re.escape(needle)+r'(?=\n\n|\Z)'
                    def replace(match):
                        fences=re.findall(r'^\s*(?:`{3,}|~{3,})',row['markdown'][:match.start()],re.M)
                        return match[0] if len(fences)%2 else quoted
                    row['markdown']=re.sub(pattern,replace,row['markdown'])

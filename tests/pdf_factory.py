"""Synthetic PDF fixture authoring with ReportLab (test-only, BSD licensed)."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader
from backend.pdf_document import Document as ParsedDocument


class Page:
    def __init__(self, document, width, height):
        self.document, self.width, self.height = document, width, height
        self.ops = []
    def insert_text(self, point, text, fontsize=11, fontname='helv', **kwargs):
        self.ops.append(('text', point, text, fontsize, fontname))
    def draw_line(self, a, b, **kwargs): self.ops.append(('line', a, b))
    def draw_rect(self, rect, **kwargs): self.ops.append(('rect', rect))
    def insert_image(self, rect, stream, **kwargs): self.ops.append(('image', rect, stream))
    def new_shape(self): return Shape(self)
    def __getattr__(self, name):
        # Direct geometry tests read the serialized fixture through the production
        # replacement adapter, never through the fixture-writing library.
        return getattr(self.document.parsed()[self.document.pages.index(self)], name)


class Shape:
    def __init__(self, page): self.page = page
    def draw_polyline(self, points):
        self.page.ops.append(('polyline', points))
    def finish(self, **kwargs): pass
    def commit(self): pass


class Document:
    def __init__(self):
        self.pages, self.toc = [], []
        self.directory = TemporaryDirectory()
        self.readers = []
    def new_page(self, width=595, height=842):
        page=Page(self,width,height);self.pages.append(page);return page
    def set_toc(self, entries): self.toc=entries
    def save(self, path):
        canvas=Canvas(str(path), invariant=1)
        for i,page in enumerate(self.pages):
            canvas.setPageSize((page.width,page.height))
            for j,(level,title,number) in enumerate(self.toc):
                if number == i+1:
                    canvas.bookmarkPage(f'b{j}')
                    canvas.addOutlineEntry(title,f'b{j}',level=level-1,closed=False)
            for op in page.ops:
                if op[0]=='text':
                    _,(x,y),text,size,font=op
                    fonts={'helv':'Helvetica','hebo':'Helvetica-Bold','heit':'Helvetica-Oblique','hebi':'Helvetica-BoldOblique','cour':'Courier','cobo':'Courier-Bold'}
                    canvas.setFont(fonts.get(font,font),size)
                    for offset, line in enumerate(text.splitlines()):
                        canvas.drawString(x,page.height-y-offset*size*1.2,line)
                elif op[0]=='line':
                    _,a,b=op;canvas.line(a[0],page.height-a[1],b[0],page.height-b[1])
                elif op[0]=='rect':
                    x0,y0,x1,y1=op[1];canvas.rect(x0,page.height-y1,x1-x0,y1-y0,stroke=1,fill=0)
                elif op[0]=='image':
                    x0,y0,x1,y1=op[1];canvas.drawImage(ImageReader(BytesIO(op[2])),x0,page.height-y1,x1-x0,y1-y0)
                elif op[0]=='polyline':
                    path=canvas.beginPath();path.moveTo(op[1][0][0],page.height-op[1][0][1])
                    for x,y in op[1][1:]:path.lineTo(x,page.height-y)
                    canvas.drawPath(path,stroke=1,fill=0)
            canvas.showPage()
        canvas.save()
    def parsed(self):
        path=Path(self.directory.name)/f'{len(self.readers)}.pdf';self.save(path)
        reader=ParsedDocument(path);self.readers.append(reader);return reader
    def close(self):
        for reader in self.readers: reader.close()
        self.directory.cleanup()

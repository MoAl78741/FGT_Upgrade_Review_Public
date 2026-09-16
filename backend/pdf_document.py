"""Job-local PDF data from pdfplumber and PDFium; no alternate extraction engine.

Coordinates use a top-left origin. Text retains content-stream order rather than
sorting columns globally. The shared session avoids reparsing pages for each
independent formatting pass and is released before the worker exits.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps, cached_property
from pathlib import Path
from types import SimpleNamespace
import re
import math
import ctypes
import pdfplumber
import pypdfium2 as pdfium
from pdfplumber.page import Page as PlumberPage, PDFPageAggregatorWithMarkedContent
from pdfminer.pdfinterp import PDFPageInterpreter

_active = ContextVar('pdf_document', default=None)


class FontEvidenceAggregator(PDFPageAggregatorWithMarkedContent):
    def render_char(self, matrix, font, fontsize, *args):
        advance = super().render_char(matrix, font, fontsize, *args)
        char = self.cur_item._objs[-1]
        char.nominal_size = abs(fontsize) * math.hypot(matrix[0], matrix[1])
        char.nominal_ascent = font.get_ascent() * char.nominal_size
        char.nominal_descent = font.get_descent() * char.nominal_size
        return advance


class EvidencePage(PlumberPage):
    @property
    def layout(self):
        if not hasattr(self, '_layout'):
            device = FontEvidenceAggregator(self.pdf.rsrcmgr, pageno=self.page_number, laparams=self.pdf.laparams)
            PDFPageInterpreter(self.pdf.rsrcmgr, device).process_page(self.page_obj)
            self._layout = device.get_result()
        return self._layout

    def process_object(self, obj):
        result = super().process_object(obj)
        if hasattr(obj, 'nominal_size'):
            result.update(nominal_size=obj.nominal_size, nominal_ascent=obj.nominal_ascent,
                          nominal_descent=obj.nominal_descent)
        return result


class Rect(tuple):
    def __new__(cls, values): return super().__new__(cls, values)
    x0 = property(lambda s: s[0]); y0 = property(lambda s: s[1])
    x1 = property(lambda s: s[2]); y1 = property(lambda s: s[3])
    width = property(lambda s: s[2] - s[0]); height = property(lambda s: s[3] - s[1])


def _bbox(items):
    return Rect((min(c['x0'] for c in items), min(c['top'] for c in items),
                 max(c['x1'] for c in items), max(c['bottom'] for c in items)))


class Page:
    def __init__(self, document, number):
        self.document, self.number = document, number
        self.source = document.plumber.pages[number]
        width, height = document.pdfium.get_page_size(number)
        self.rect = Rect((0, 0, width, height))

    @cached_property
    def lines(self):
        groups = []
        links = self.get_links()
        def link_for(char):
            x, y = (char['x0']+char['x1'])/2, self.rect.height-char['matrix'][5]
            return next((link['uri'] for link in links if link['from'][0] <= x <= link['from'][2]
                         and link['from'][1]-2 <= y <= link['from'][3]+2), None)
        # Group consecutive glyphs by baseline and visual continuity. Keep separate
        # text columns separate even when they share a baseline.
        for char in self.source.chars:
            if not char.get('text'): continue
            baseline = self.rect.height - char['matrix'][5]
            if groups:
                prior = groups[-1][-1]
                prior_base = self.rect.height - prior['matrix'][5]
                gap = char['x0'] - prior['x1']
                crosses_border = gap > 1 and any(edge.get('orientation') == 'v' and prior['x1'] < edge['x0'] <= char['x0']
                                     and edge['top'] <= baseline <= edge['bottom'] for edge in self.source.edges)
                if abs(baseline-prior_base) <= 2 and -2 <= gap <= max(10, char['nominal_size'] * 1.5) and not crosses_border:
                    groups[-1].append(char); continue
            groups.append([char])
        result = []
        for chars in groups:
            spans, span_chars = [], []
            def flush():
                if not span_chars: return
                bounds = _bbox(span_chars)
                first = span_chars[0]
                baseline = self.rect.height-first['matrix'][5]
                bounds = Rect((bounds.x0, baseline-first['nominal_ascent'], bounds.x1, baseline-first['nominal_descent']))
                spans.append({'text': ''.join(c['text'] for c in span_chars),
                              'font': re.sub(r'^[A-Z]{6}\+', '', span_chars[0]['fontname']),
                              'size': first['nominal_size'], 'bbox': bounds})
            for char in chars:
                prior = span_chars[-1] if span_chars else None
                if prior and char['x0']-prior['x1'] > char['nominal_size']*.18 and not prior['text'].endswith(' '):
                    span_chars.append({**prior, 'text': ' ', 'x0': prior['x1'], 'x1': char['x0']})
                if span_chars and (char['fontname'], char['size'], link_for(char)) != (prior['fontname'], prior['size'], link_for(prior)):
                    flush(); span_chars = []
                span_chars.append(char)
            flush()
            result.append({'bbox': Rect((min(s['bbox'][0] for s in spans), min(s['bbox'][1] for s in spans),
                                        max(s['bbox'][2] for s in spans), max(s['bbox'][3] for s in spans))), 'spans': spans})
        return result

    def get_text(self, mode='text', clip=None):
        if mode != 'dict': return self.source.extract_text() or ''
        lines = self.lines
        if clip:
            lines = [{**line, 'spans': [s for s in line['spans'] if
                      clip[0] <= (s['bbox'][0]+s['bbox'][2])/2 <= clip[2] and
                      clip[1] <= (s['bbox'][1]+s['bbox'][3])/2 <= clip[3]]} for line in lines]
            lines = [line for line in lines if line['spans']]
        return {'blocks': [{'type': 0, 'lines': lines}]}

    def get_links(self):
        return [{'uri': a['uri'], 'from': Rect((a['x0'], a['top'], a['x1'], a['bottom']))}
                for a in self.source.hyperlinks if a.get('uri')]

    def get_textbox(self, rect):
        return ' '.join(''.join(s['text'] for s in line['spans'])
                        for block in self.get_text('dict', clip=rect)['blocks'] for line in block['lines'])

    @cached_property
    def tables(self):
        from .pdf_parser import _complete_left_column
        result = []
        for table in self.source.find_tables():
            complete = _complete_left_column(self.source, table)
            if complete is not table:
                def extract(x_tolerance=3, y_tolerance=3, target=complete):
                    return [[self.source.crop(cell).extract_text(x_tolerance=x_tolerance, y_tolerance=y_tolerance)
                             if cell else None for cell in row.cells] for row in target.rows]
                complete.extract = extract
            result.append(complete)
        return result
    def find_tables(self): return SimpleNamespace(tables=self.tables)
    def get_image_info(self):
        return [{'bbox': (im['x0'], im['top'], im['x1'], im['bottom'])} for im in self.source.images]
    def get_drawings(self):
        drawings = []
        for obj in self.source.rects + self.source.curves + self.source.lines:
            rect = Rect((obj['x0'], obj['top'], obj['x1'], obj['bottom']))
            if obj['object_type'] == 'rect': items = [('re', rect)]
            else:
                pts = obj.get('pts', [(rect.x0, rect.y0), (rect.x1, rect.y1)])
                items = [('l', SimpleNamespace(x=a[0], y=a[1]), SimpleNamespace(x=b[0], y=b[1])) for a,b in zip(pts, pts[1:])]
            drawings.append({'rect': rect, 'items': items})
        return drawings

    def render(self, scale=1):
        # Caller owns the returned bitmap; page lifetime ends here.
        page = self.document.pdfium[self.number]
        try: return page.render(scale=scale)
        finally: page.close()


class Document:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.pdfium = pdfium.PdfDocument(str(self.path))
        try: self.plumber = pdfplumber.open(self.path)
        except BaseException:
            self.pdfium.close(); raise
        self.plumber._pages = [EvidencePage(self.plumber, page.page_obj, page.page_number, page.initial_doctop)
                               for page in self.plumber.pages]
        self.pages = {}
    def __len__(self): return len(self.pdfium)
    def __getitem__(self, index):
        if index < 0 or index >= len(self): raise IndexError(index)
        if index not in self.pages: self.pages[index] = Page(self, index)
        return self.pages[index]
    def __iter__(self): return (self[n] for n in range(len(self)))
    def __enter__(self): return self
    def __exit__(self, *args):
        if _active.get() is not self: self.close()
    def close(self):
        self.pages.clear(); self.plumber.close(); self.pdfium.close()
    def get_toc(self):
        result = []
        for bookmark in self.pdfium.get_toc(max_depth=64):
            dest = bookmark.get_dest()
            result.append([bookmark.level+1, bookmark.get_title(), dest.get_index()+1 if dest else -1])
        return result
    @property
    def metadata(self):
        values = self.pdfium.get_metadata_dict()
        version = ctypes.c_int()
        known = pdfium.raw.FPDF_GetFileVersion(self.pdfium, ctypes.byref(version))
        fields = {'title':'Title', 'author':'Author', 'subject':'Subject', 'keywords':'Keywords',
                  'creator':'Creator', 'producer':'Producer', 'creationDate':'CreationDate', 'modDate':'ModDate'}
        return {'format': f'PDF {version.value//10}.{version.value%10}' if known else '',
                **{key: values.get(value, '') for key,value in fields.items()},
                'trapped': self.pdfium.get_metadata_value('Trapped'),
                'encryption': None if pdfium.raw.FPDF_GetSecurityHandlerRevision(self.pdfium) < 0 else 'encrypted'}


def open_document(path):
    active = _active.get()
    return active if active and active.path == Path(path).resolve() else Document(path)


@contextmanager
def plumber_document(path):
    with open_document(path) as document: yield document.plumber


def pdf_session(function):
    @wraps(function)
    def run(path, *args, **kwargs):
        if _active.get() is not None: return function(path, *args, **kwargs)
        document = Document(path)
        token = _active.set(document)
        try: return function(path, *args, **kwargs)
        finally:
            _active.reset(token); document.close()
    return run

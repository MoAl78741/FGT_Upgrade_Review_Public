"""Replacement engine exclusion, metadata and malformed/encrypted input checks."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pdfencrypt import StandardEncryption
from backend.pdf_document import Document


def test_removed_engine_is_not_importable():
    for name in ('pymupdf','fitz','pymupdf4llm','pymupdf_layout'):
        assert importlib.util.find_spec(name) is None


def test_metadata_outline_count_and_raster_are_available(tmp_path):
    path=tmp_path/'metadata.pdf';canvas=Canvas(str(path));canvas.setTitle('Metadata test')
    canvas.bookmarkPage('first');canvas.addOutlineEntry('Chapter','first');canvas.drawString(50,700,'Source text');canvas.save()
    with Document(path) as document:
        assert len(document)==1
        assert document.metadata['title']=='Metadata test'
        assert document.get_toc()==[[1,'Chapter',1]]
        bitmap=document[0].render(scale=.5)
        try: assert bitmap.width > 200 and bitmap.height > 200
        finally: bitmap.close()


def preflight(path):
    output=path.with_suffix('.json')
    environment={**os.environ,'JOB_TIMEOUT_SECONDS':'60','WORKER_MEMORY_BYTES':str(512*1024**2),'MAX_PDF_PAGES':'10'}
    result=subprocess.run([sys.executable,'-m','backend.parse_process',str(path),str(output),'--metadata-only'],env=environment,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    return json.loads(output.read_text())


def test_damaged_pdf_is_rejected_actionably(tmp_path):
    path=tmp_path/'damaged.pdf';path.write_bytes(b'%PDF-1.7\nNot a document')
    assert 'Invalid or damaged PDF' in preflight(path)['error']


def test_encrypted_pdf_is_rejected_even_with_empty_user_password(tmp_path):
    for index,password in enumerate(('secret','')):
        path=tmp_path/f'encrypted-{index}.pdf'
        canvas=Canvas(str(path),encrypt=StandardEncryption(password,ownerPassword='owner-secret'))
        canvas.drawString(50,700,'Private');canvas.save()
        assert 'Encrypted PDFs are not supported' in preflight(path)['error']

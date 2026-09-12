"""Keep release-specific source content when importing multiple PDFs."""
import json
from unittest.mock import Mock

from backend import pdf_worker, pdf_parser


def test_same_title_notices_preserve_every_versions_text(monkeypatch, tmp_path):
    job = Mock(log='')
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = job
    monkeypatch.setattr(pdf_worker, 'SessionLocal', lambda: db)
    monkeypatch.setattr(pdf_worker, 'UPLOADS_DIR', tmp_path)
    monkeypatch.setattr(pdf_parser, 'PDF_AVAILABLE', True)
    versions = ['7.2.8', '7.2.9', '7.4.3', '7.4.11']
    parsed = [(v, {}, [{'title': 'Shared title', 'content': f'Instructions for {v}'}], {}, {}) for v in versions]
    monkeypatch.setattr(pdf_parser, 'parse_pdf', Mock(side_effect=parsed))
    pdf_worker.run_pdf_job('test', [f'{v}.pdf' for v in versions])
    assert job.status == 'completed'
    notices = json.loads(job.special_notices_json)
    assert [n['version'] for n in notices] == versions
    assert [n['content'] for n in notices] == [f'Instructions for {v}' for v in versions]

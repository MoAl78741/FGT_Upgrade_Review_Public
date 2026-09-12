import pymupdf
import pytest
from backend.pdf_table_format import add_table_formatting


@pytest.mark.parametrize('headers', [('Before upgrade', 'After upgrade'), ('Old syntax', 'New syntax'), ('Example A', 'Example B')])
@pytest.mark.parametrize('command', ['config', 'show', 'get'])
def test_cli_cells_retain_source_rows_and_column_order(tmp_path, headers, command):
    path=tmp_path/'commands.pdf';doc=pymupdf.open();page=doc.new_page(width=612,height=792)
    page.draw_rect((50,90,550,310));page.draw_line((300,90),(300,310))
    for y in [120,215]:page.draw_line((50,y),(550,y))
    page.insert_text((60,110),headers[0],fontsize=10);page.insert_text((310,110),headers[1],fontsize=10)
    rows=[['config system first\n    set option old\nend','config system first\n    set option new\nend'],
          ['config system second\n    set option old\nend','config system second\n    set option new\nend']]
    rows = [[cell.replace('config', command) for cell in row] for row in rows]
    for row,y in zip(rows,[145,240]):
        for text,x in zip(row,[60,310]):page.insert_text((x,y),text,fontsize=10,fontname='cour')
    doc.save(path);doc.close()
    table={'type':'table','headers':list(headers),'rows':[[' '.join(c.split()) for c in row] for row in rows]}
    data={'examples':{'title':'Examples','blocks':[table]}}
    add_table_formatting(path,data,{'examples':[0]})
    assert len(table['rows']) == 2
    assert table['headers'] == list(headers)
    for index in range(2):
        left, right = table['cellMarkdown'][index]
        assert left == '```\n' + rows[index][0] + '\n```'
        assert right == '```\n' + rows[index][1] + '\n```'
        assert 'option new' not in left


def test_native_code_cell_keeps_blank_line_between_command_groups():
    from backend.pdf_table_format import _cell_code_markdown
    values = [('config first', 100), ('end', 112), ('config second', 136), ('end', 148)]
    lines = [{'text': text, 'inline': text, 'x': 60, 'y': y, 'size': 10,
              'page': 0, 'code': True, 'bullet': False} for text, y in values]
    assert _cell_code_markdown(lines) == '```\nconfig first\nend\n\nconfig second\nend\n```'
    # A page boundary alone is not evidence of a blank source line.
    lines[2]['page'] = lines[3]['page'] = 1
    assert 'end\n\nconfig second' not in _cell_code_markdown(lines)

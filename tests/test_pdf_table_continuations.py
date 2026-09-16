from tests.pdf_factory import Document
from backend.pdf_table_continuations import restore_table_continuations


def test_bordered_single_row_rejoins_previous_page_table(tmp_path):
    pdf=tmp_path/'continued.pdf';doc=Document();page=doc.new_page()
    page.insert_text((60,700),'Previous');page.insert_text((220,700),'Value')
    page=doc.new_page()
    for left,right in [(57,206),(206,555)]:
        shape=page.new_shape();shape.draw_polyline([(left,72),(right,72),(right,94),(left,94)]);shape.finish();shape.commit()
    page.insert_text((62,86),'Last row');page.insert_text((220,86),'Last value')
    doc.save(pdf);doc.close()
    table={'type':'table','headers':[], 'rows':[['Previous','Value']]}
    data={'section':{'blocks':[table,{'type':'paragraph','text':'Last row'}, {'type':'list','items':['Last value']}]}}
    restore_table_continuations(pdf,data,{'section':[0,1]})
    assert table['rows']==[['Previous','Value'],['Last row','Last value']]
    assert len(data['section']['blocks'])==1
    restore_table_continuations(pdf,data,{'section':[0,1]})
    assert len(table['rows'])==2
    # An unrelated preceding table must not absorb the same bordered text.
    other={'section':{'blocks':[{'type':'table','rows':[['Other','Value']]}, {'type':'paragraph','text':'Last row'}, {'type':'list','items':['Last value']}]}}
    restore_table_continuations(pdf,other,{'section':[0,1]})
    assert len(other['section']['blocks'])==3

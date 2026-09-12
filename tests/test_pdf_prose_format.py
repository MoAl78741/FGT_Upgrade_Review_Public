from backend.pdf_prose_format import _prose_blocks


def line(text, x, y, bullet=False):
    return {'text': text, 'inline': text, 'x': x, 'y': y, 'page': 0, 'size': 10, 'bullet': bullet}


def test_ordered_steps_keep_nested_bullets_in_one_sequence():
    blocks = _prose_blocks([line('1. Entry policy:', 60, 100), line('External to loopback', 85, 120, True),
        line('2. Exit policy:', 60, 145), line('Loopback to server', 85, 165, True)])
    assert len(blocks) == 1 and blocks[0]['ordered']
    assert blocks[0]['items'] == ['Entry policy:', 'Exit policy:']
    assert blocks[0]['itemBlocks'][0][1]['items'] == ['External to loopback']
    assert blocks[0]['itemBlocks'][1][1]['items'] == ['Loopback to server']


def test_nested_bullets_outdent_to_the_correct_parent():
    blocks = _prose_blocks([line('Formats:', 70, 100, True), line('XVA', 85, 120, True),
        line('VHD', 85, 140, True), line('Other restrictions.', 70, 160, True)])
    assert blocks[0]['items'] == ['Formats:', 'Other restrictions.']
    assert blocks[0]['itemBlocks'][0][1]['items'] == ['XVA', 'VHD']


def test_line_wrapping_does_not_insert_space_into_a_hyphenated_word():
    blocks = _prose_blocks([line('Use loopback-', 57, 100), line('based VIPs.', 57, 113)])
    assert blocks[0]['text'] == 'Use loopback-based VIPs.'
    assert blocks[0]['markdown'] == 'Use loopback-based VIPs.'


def test_body_paragraph_after_numbered_steps_is_not_part_of_the_last_step():
    blocks = _prose_blocks([line('1. Entry policy:', 57, 100), line('External traffic', 80, 120, True),
                           line('See also the guide.', 57, 145)])
    assert [b['type'] for b in blocks] == ['list', 'paragraph']
    assert blocks[0]['items'] == ['Entry policy:']
    assert blocks[-1]['text'] == 'See also the guide.'


def test_steps_keep_code_and_note_inside_their_list_item():
    code = {**line('config system ha', 73, 120), 'code': True, 'leading_space': ''}
    note = {**line('A warning.', 130, 150), 'source_block': {'type': 'paragraph', 'text': 'A warning.', 'markdown': '> A warning.', 'source_note': True}}
    blocks = _prose_blocks([line('1. Configure HA:', 57, 100), code, note, line('2. Check status.', 57, 180)])
    assert len(blocks) == 1
    assert [b['type'] for b in blocks[0]['itemBlocks'][0]] == ['paragraph', 'code', 'paragraph']
    assert blocks[0]['itemBlocks'][0][1]['text'] == 'config system ha'
    assert blocks[0]['itemBlocks'][0][2]['source_note']
    assert blocks[0]['items'][1] == 'Check status.'


def test_notice_uses_matching_section_format_without_overwriting_source_content():
    from backend.pdf_prose_format import sync_notice_formatting
    data = {'upgrade-warning': {'title': 'Upgrade warning', 'blocks': [{'type': 'paragraph', 'text': 'Original text.', 'markdown': '**Original** text.'}]}}
    notices = [{'title': 'Upgrade warning', 'content': 'Original text.', 'markdown': 'Old formatting'}, {'title': 'Other', 'content': 'Keep this.'}]
    sync_notice_formatting(data, notices)
    assert notices[0]['content'] == 'Original text.'
    assert 'markdown' not in notices[0]
    assert notices[0]['blocks'] == data['upgrade-warning']['blocks']
    assert notices[0]['blocks'] is not data['upgrade-warning']['blocks']
    assert notices[1] == {'title': 'Other', 'content': 'Keep this.'}


def test_two_digit_number_alignment_does_not_split_the_sequence():
    blocks = _prose_blocks([line('9. Nine', 57, 100), line('10. Ten', 52, 120)])
    assert len(blocks) == 1 and blocks[0]['start'] == 9
    assert blocks[0]['items'] == ['Nine', 'Ten']


def test_wrapped_inline_code_is_not_mistaken_for_a_code_block():
    inline = {**line('domain\\username.', 57, 113), 'code': True, 'inline': '` domain\\username `.'}
    blocks = _prose_blocks([line('Enter credentials in the form of', 57, 100), inline])
    assert [b['type'] for b in blocks] == ['paragraph']
    assert blocks[0]['markdown'].endswith('form of ` domain\\username `.')

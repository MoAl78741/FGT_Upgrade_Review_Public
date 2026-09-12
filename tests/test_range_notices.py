from backend.scrape_worker import _collect_range_notices


def test_notices_retain_version_and_changed_same_title():
    data = {'7.4.0': {}, '7.4.1': {}}
    notices = _collect_range_notices(list(data), data, lambda version: [
        {'title': 'Upgrade warning', 'content': 'Instructions for ' + version}])
    assert [n['version'] for n in notices] == ['7.4.0', '7.4.1']
    assert notices[0]['content'] != notices[1]['content']
    assert 'version' not in data['7.4.0']['_special_notices'][0]
    assert _collect_range_notices(list(data), data, lambda _: (_ for _ in ()).throw(AssertionError('Cached release refetched'))) == notices


def test_empty_notice_result_is_cached_and_not_filled_from_another_release():
    data = {'7.4.0': {'_special_notices': []}, '7.4.1': {}}
    requested = []
    def fetch(version):
        requested.append(version)
        return [{'title': 'Only here', 'content': 'Warning'}]
    notices = _collect_range_notices(list(data), data, fetch)
    assert requested == ['7.4.1']
    assert len(notices) == 1 and notices[0]['version'] == '7.4.1'

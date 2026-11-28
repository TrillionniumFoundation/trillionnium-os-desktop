"""Original package identity through the retained normal APK custody owner."""
def identity(session,package,expected_sha,expected_uid=None,expected_code=1):
    channel=session.baseline.live
    fixture=channel.fixture()
    if package==fixture.spec['package']:
        value=fixture.identity()
        if (value['apk_sha256']!=expected_sha or value['version_code']!=expected_code
            or (expected_uid is not None and value['uid']!=expected_uid)):
            raise RuntimeError('ACTUAL_FIXED_HELPER_IDENTITY_DIFFERS')
        return value
    return channel.original_identity(package,expected_sha,expected_uid,expected_code)

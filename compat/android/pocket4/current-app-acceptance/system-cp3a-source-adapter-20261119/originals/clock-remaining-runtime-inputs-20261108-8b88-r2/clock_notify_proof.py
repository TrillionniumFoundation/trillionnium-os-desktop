"""Pure evidence joins for this sole owned timer; no device or bus operations."""
import hashlib, re

KEY='0|com.android.deskclock|2147483644|null|10063'


def parse_nms(raw):
    """Exact filtered active records only. Unknown/redacted text stays unqualified."""
    result={'parsed':False,'records':[],'raw_sha256':hashlib.sha256(raw).hexdigest()}
    try:
        lines=raw.decode('utf-8','strict').splitlines()
        assert lines[0]=="Current Notification Manager state (filtered to 'com.android.deskclock'):"
        starts=[i for i,line in enumerate(lines) if line=='  Notification List:'];assert len(starts)==1
        body=[]
        for line in lines[starts[0]+1:]:
            if line.strip() and not line.startswith('    '):break
            body.append(line)
        if not ''.join(body).strip():result['parsed']=True;return result
        blocks=re.split(r'(?=^    NotificationRecord\()', '\n'.join(body),flags=re.M)
        assert not blocks[0].strip()
        for block in blocks[1:]:
            header=block.splitlines()[0]
            assert re.search(r'\bpkg=com\.android\.deskclock\b',header) and 'user=UserHandle{0}' in header
            assert re.search(r'^      uid=10063 userId=0$',block,re.M)
            keys=re.findall(r'^      key=(\S+)$',block,re.M);assert len(keys)==1
            extras=re.findall(r'^            extras=\{\n(.*?)^            \}',block,re.M|re.S)
            assert len(extras)==1
            values={}
            for name in ('android.title','android.text','android.bigText','android.textLines'):
                matches=re.findall(r'^                '+re.escape(name)+r'=(.*)$',extras[0],re.M)
                assert len(matches)<=1
                value=matches[0] if matches else 'null'
                if value=='null':values[name]=None;continue
                found=re.fullmatch(r'String \((.*)\)',value);assert found
                text=found[1];assert text and not text.startswith('length=') and '\x00' not in text
                assert len(text)<=2048
                values[name]=text
            post=re.findall(r'\bposttimeElapsedMs=(\d+)\b',block);assert len(post)==1
            result['records'].append({'key':keys[0],'uid':10063,'user':0,
                'title':values['android.title'],'text':values['android.text'],
                'alternate_body_present':any(values[k] is not None for k in ('android.bigText','android.textLines')),
                'post_elapsed_ms':int(post[0]),'full_screen_pending_intent':bool(re.search(r'\bfullscreenIntent=PendingIntent\{',block)),
                'timer_channel':bool(re.search(r'\bchannel=TimerModelNotification\b',block)),
                'record_sha256':hashlib.sha256(block.encode()).hexdigest()})
        result['parsed']=True
    except (AssertionError,IndexError,UnicodeError):result['reason']='EXACT_ACTIVE_TEXT_GRAMMAR_UNVERIFIED'
    return result


def associate(expired,running,observed,running_observed,basis,due_ms):
    """Match exact expiry text + source key + post/receive time, never arbitrary Clock text."""
    out={'verified':False,'key':KEY,'absence_is_not_App_failure':True,
        'desktop_popup_observed':False,'running_text_excluded':False,'matched_calls':[]}
    try:
        assert expired['parsed'] is True and running['parsed'] is True
        records=[r for r in expired['records'] if r['key']==KEY];assert len(records)==1
        record=records[0]
        assert record['uid']==10063 and record['user']==0 and record['timer_channel'] and record['full_screen_pending_intent']
        assert not record['alternate_body_present'] and record['title'] and record['text']
        assert due_ms<=record['post_elapsed_ms']<=due_ms+30000
        # Actual host body-markup support escapes these characters in Notify.
        escaped=record['text'].replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
        pair=(record['title'],escaped)
        assert all(r['key']!=KEY for r in running['records'])
        assert pair not in {(r['title'],r['text']) for r in running['records']}
        assert pair not in {(r['title'],r['body']) for r in running_observed['raw_calls']}
        assert running_observed['own_state']['record'] is None
        assert type(basis['before_ns']) is int and type(basis['after_ns']) is int
        assert 0<=basis['after_ns']-basis['before_ns']<=2000000000
        earliest_due_ns=basis['before_ns']+(due_ms-basis['uptime_ms'])*1000000
        latest_due_ns=basis['after_ns']+(due_ms-basis['uptime_ms']+30000)*1000000
        current=observed['own_state']
        assert current['key']==KEY and observed['baseline']['record'] is None
        state=current['record'];assert state and type(state['id']) is int and state['id']>0 and state['hidden'] is False
        assert observed['id_changed'] and observed['version_changed'] and not observed['errors']
        boundary=running_observed['raw_stdout_bytes'];assert type(boundary) is int and boundary>=0
        matches=[]
        for call in observed['raw_calls']:
            timing=call.get('local_receive',{})
            received=timing.get('monotonic_ns');span=timing.get('line_byte_range',[])
            if not (isinstance(received,str) and received.isdecimal() and len(span)==2):continue
            received=int(received);end=span[1]
            if ((call['title'],call['body'])==pair
                and timing.get('source')=='local_read_completion_not_sender_or_delivery_timestamp'
                and timing.get('receive_time_is_upper_bound') is True
                and earliest_due_ns<=received<=latest_due_ns
                and type(span[0]) is int and span[0]>=boundary
                and type(end) is int and end>span[0]):matches.append(call)
        assert matches
        out.update(verified=True,running_text_excluded=True,matched_calls=matches,
            NMS_record=record,host_record=state,receive_after_offset=boundary,
            receive_due_window_ns=[str(earliest_due_ns),str(latest_due_ns)],clock_basis=basis,
            sender_timestamp_proven=False,exact_NMS_pair_received_after_due=True)
    except (AssertionError,KeyError,TypeError):out['reason']='EXPIRED_TEXT_TIME_OR_IDENTITY_ASSOCIATION_UNVERIFIED'
    return out


def monitor_closed(stop,child_started):
    """Cleanup is a positive return-value check, not merely absence of exceptions."""
    if not isinstance(stop,dict):return False
    if child_started is False:
        return bool(stop.get('child_joined') is False and stop.get('returncode') is None
            and stop.get('reader_joined') is True and stop.get('cleanup_error') is None)
    return bool(child_started is True and stop.get('child_joined') is True
        and stop.get('reader_joined') is True and stop.get('all_owned_monitor_writers_closed') is True
        and stop.get('pipe_eof')=={'stdout':True,'stderr':True} and stop.get('cleanup_error') is None)


PLAYER_BUTTON_RESOURCE = PACKAGE+':id/gemini_halfscreen_play'
PLAYER_BUTTON_LABELS = {'pause':'暂停','resume':'播放'}
MAX_PLAYER_SELECTION_AGE_MS = 1000


def player_frame(proof):
    keys=('scope','window','window_sha256','viewport_bounds','full_area_bounds',
          'render_structure_sha256','title_text_sha256','author_text_sha256')
    return {key:proof[key] for key in keys}


def player_button_current(inspection,host_scope,transition):
    """Fixed current role, never caller coordinates or an arbitrary selector."""
    require(transition in PLAYER_BUTTON_LABELS,'FIXED_PLAYER_TRANSITION_REQUIRED')
    proof=player_reveal_scope(inspection,host_scope,False)
    nodes=inspection['nodes'];by_path={n['path']:n for n in nodes}
    rows=[n for n in nodes if n.get('resource_id')==PLAYER_BUTTON_RESOURCE]
    require(len(rows)==1,'UNIQUE_CURRENT_PLAYBACK_RESOURCE_REQUIRED')
    label=PLAYER_BUTTON_LABELS[transition]
    target=select_unique_clickable(inspection,{'resource_id':PLAYER_BUTTON_RESOURCE,
        'class':'android.widget.ImageView','content_desc':label})
    node=rows[0];controls=[n for n in nodes if n.get('resource_id')==PACKAGE+':id/control_container']
    require(len(controls)==1,'UNIQUE_CURRENT_CONTROL_CONTAINER_REQUIRED')
    controls=controls[0]
    containers=[n for n in nodes if n.get('resource_id')==PACKAGE+':id/video_container']
    require(len(containers)==1,'UNIQUE_CURRENT_VIDEO_CONTAINER_REQUIRED')
    parent=by_path.get(node['path'].rsplit('/',1)[0]);crop=proof['viewport_bounds'];bounds=reveal_rect(node['bounds'])
    def eligible(n):
        return isinstance(n,dict) and n.get('visible') is True and n.get('enabled') is True and n.get('password') is False and n.get('class_truncated') is False and n.get('resource_id_truncated') is False
    require(eligible(controls) and controls['class']=='android.widget.FrameLayout' and
        controls['path'].startswith(containers[0]['path']+'/') and controls['bounds']==crop and
        type(controls['child_count']) is int and controls['child_count']==1 and
        eligible(parent) and parent['class']=='android.view.ViewGroup' and parent['resource_id']=='' and
        parent['path'].rsplit('/',1)[0]==controls['path'] and parent['bounds']==crop and
        node['editable'] is False and node['text']=='' and node['text_truncated'] is False and
        node['content_desc_sha256']==sha(label.encode()) and
        crop[0]<=bounds[0]<bounds[2]<=crop[2] and crop[1]<=bounds[1]<bounds[3]<=crop[3] and
        target=={'node_path':node['path'],'node_sha256':node['node_sha256']},
        'EXACT_CURRENT_PLAYER_DIRECT_CONTROL_REQUIRED')
    return target,proof


def player_button_request_fields(inspection,host_scope,transition):
    _,proof=player_button_current(inspection,host_scope,transition)
    return {'transition':transition,'player_frame_sha256':sha(canonical(player_frame(proof)))}


def assess_player_button(value,request,observed_window,observed_trees):
    require(value.get('action_attempted') is True and value.get('outcome_unknown') is True and
        value.get('node_action')=='ACTION_CLICK' and value.get('node_action_returned') is True and
        value.get('inspection_nonce')==request['inspection_nonce'] and
        value.get('inspection_sha256')==request['inspection_sha256'] and
        value.get('transition')==request['transition'] and
        value.get('player_frame_sha256')==request['player_frame_sha256'] and
        value.get('prior_inspection_is_context_only') is True and
        value.get('atomic_android_transaction') is False and
        value.get('same_connection_full_tree_rechecks')==2,
        'CURRENT_PLAYER_BUTTON_REQUEST_AND_ACK_REQUIRED')
    current=inspect_record(value.get('player_inspection'))
    target,proof=player_button_current(current,request['scope'],request['transition'])
    require(value.get('player_scope')==proof and
        sha(canonical(player_frame(proof)))==request['player_frame_sha256'] and
        value.get('player_inspection_sha256')==sha(canonical(current)) and
        value.get('target_node_path')==target['node_path'] and
        value.get('target_node_sha256')==target['node_sha256'] and
        value.get('action_window')==current['window'] and
        value.get('connection_scoped_window_id')==current['connection_scoped_window_id']==observed_window['selected_window_id'],
        'CURRENT_PLAYER_CAPTURE_ROLE_AND_CONTEXT_REQUIRED')
    captures=value.get('player_capture_bindings')
    require(type(captures) is list and len(captures)==3,'THREE_CURRENT_PLAYER_CAPTURE_BINDINGS_REQUIRED')
    previous=current['observed_elapsed_ms']
    for index,row in enumerate(captures):
        require(type(row) is dict and set(row)=={'tree_sha256','window_sha256','connection_scoped_window_id','observed_elapsed_ms'} and
            row['tree_sha256']==current['tree_sha256'] and row['window_sha256']==current['window_sha256'] and
            type(row['connection_scoped_window_id']) is int and row['connection_scoped_window_id']==current['connection_scoped_window_id'] and
            type(row['observed_elapsed_ms']) is int and previous<=row['observed_elapsed_ms'],
            'CURRENT_PLAYER_WHOLE_TREE_WINDOW_OR_CAPTURE_ORDER_CHANGED')
        require(observed_trees[index]['emitted_nodes']==len(current['nodes']) and
            observed_trees[index]['began_elapsed_ms']<=row['observed_elapsed_ms']<=observed_trees[index]['last_elapsed_ms'],
            'CURRENT_PLAYER_COMPLETE_CAPTURE_TIMING_REQUIRED')
        previous=row['observed_elapsed_ms']
    require(captures[0]['observed_elapsed_ms']==current['observed_elapsed_ms'] and
        observed_trees[0]['serialized_bytes']==len(canonical(current)) and
        type(value.get('player_action_admitted_elapsed_ms')) is int and
        value['started_elapsed_ms']<=current['observed_elapsed_ms']<=previous<=value['player_action_admitted_elapsed_ms']<=value['finished_elapsed_ms'] and
        type(value.get('player_selection_age_ms')) is int and
        value['player_selection_age_ms']==value['player_action_admitted_elapsed_ms']-current['observed_elapsed_ms'] and
        0<=value['player_selection_age_ms']<=MAX_PLAYER_SELECTION_AGE_MS and
        value.get('player_selection_age_limit_ms')==MAX_PLAYER_SELECTION_AGE_MS,
        'CURRENT_PLAYER_SELECTION_FRESHNESS_REQUIRED')

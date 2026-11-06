"""Only discovery's first actual New event Button uses the existing snapshot tap."""
import time

LABEL='core-discover-01-open-new'
PACKAGE='com.android.calendar'
ACTIVITY='com.android.calendar.AllInOneActivity'
MAX_READS=6

def normal(node):
    if not isinstance(node,dict) or type(node.get('window_id')) is not int or node['window_id']<0:
        raise RuntimeError('FIRST_OPEN_CONNECTION_ID_REQUIRED')
    return {k:v for k,v in node.items() if k!='window_id'}

def complete_target(base,semantic,value,node,obs):
    context=value.get('window_context',{});selected=context.get('selected_window',{})
    root=context.get('root',{})
    base.need(value.get('ok') is True and value.get('outcome_unknown') is not True
        and value.get('accessibility_mode_restoration_verified') is True
        and context.get('snapshot_complete') is True and context.get('tree_status')=='available'
        and context.get('semantic_controls_available') is True
        and context.get('null_child_count')==0 and context.get('truncated') is False,
        'FIRST_OPEN_COMPLETE_NATIVE_TREE_REQUIRED')
    selector=semantic.selector_for(node)
    found=[n for n in value.get('nodes',[]) if semantic.selector_matches(n,selector)]
    base.need(len(found)==1 and normal(found[0])==normal(node),'FIRST_OPEN_FULL_UNIQUE_NODE_CHANGED')
    target=found[0];window=target['window_id']
    base.need(selected.get('active') is True and selected.get('focused') is True
        and selected.get('display_id')==0 and selected.get('window_id')==window
        and root.get('window_id')==window and root.get('package')==PACKAGE
        and root.get('visible') is True and root.get('present') is True
        and selected.get('bounds')==root.get('bounds')==obs['screenshot']['scope_bounds'],
        'FIRST_OPEN_NATIVE_WINDOW_OR_GEOMETRY_CHANGED')
    observed=[normal(n) for n in obs['nodes']]
    fresh=[normal(n) for n in value.get('nodes',[])]
    base.need(fresh==observed,'FIRST_OPEN_COMPLETE_NODE_SET_CHANGED')
    return fresh

def waitable_content_null(base,semantic,value,node,obs):
    """Recognize only the exact retained16 partial-tree shape; never authorizes input."""
    context=value.get('window_context',{})
    if not (value.get('ok') is True and value.get('outcome_unknown') is not True
        and value.get('accessibility_mode_restoration_verified') is True
        and context.get('snapshot_complete') is False and context.get('tree_status')=='incomplete'
        and context.get('semantic_controls_available') is False
        and type(context.get('null_child_count')) is int and context['null_child_count']==1
        and context.get('truncated') is False):return False
    selected=context.get('selected_window',{});root=context.get('root',{});window=root.get('window_id')
    base.need(type(window) is int and window>=0 and selected.get('window_id')==window
        and selected.get('active') is True and selected.get('focused') is True
        and selected.get('display_id')==0 and root.get('package')==PACKAGE
        and root.get('visible') is True and root.get('present') is True
        and root.get('class')=='android.widget.FrameLayout' and root.get('child_count')==3
        and selected.get('root')==root
        and selected.get('bounds')==root.get('bounds')==obs['screenshot']['scope_bounds'],
        'FIRST_OPEN_PARTIAL_WINDOW_CHANGED')
    original=[normal(n) for n in obs['nodes']];fresh=[normal(n) for n in value.get('nodes',[])]
    missing=[n for n in original if n not in fresh]
    base.need(len(original)==24 and len(fresh)==23 and len(missing)==1
        and fresh==[n for n in original if n!=missing[0]]
        and type(context.get('visited_count')) is int and context['visited_count']==24
        and type(context.get('visible_count')) is int and context['visible_count']==23
        and all(n.get('window_id')==window for n in value['nodes']),
        'FIRST_OPEN_PARTIAL_NODE_SET_CHANGED')
    content=missing[0];bounds=content.get('bounds_array');scope=obs['screenshot']['scope_bounds']
    base.need(content.get('package')==PACKAGE and content.get('class')=='android.view.View'
        and content.get('resource-id')==content.get('text')==content.get('content-desc')==''
        and content.get('focused') is True and content.get('clickable') is True
        and content.get('visible') is True and content.get('enabled') is True
        and content.get('editable') is False and content.get('password') is False
        and isinstance(bounds,list) and len(bounds)==4 and all(type(v) is int for v in bounds)
        and bounds[0]==scope[0] and bounds[2]==scope[2]
        and node['bounds_array'][3]<bounds[1]<bounds[3]<=scope[3],
        'FIRST_OPEN_UNRECOGNIZED_MISSING_NODE')
    matches=[n for n in value['nodes'] if semantic.selector_matches(n,semantic.selector_for(node))]
    base.need(len(matches)==1 and normal(matches[0])==normal(node),'FIRST_OPEN_PARTIAL_TARGET_CHANGED')
    return True

def extend(base,semantic):
    original_pointer=base.Adapter
    original_semantic=semantic.extend(base)
    class FirstOpenSnapshot(original_semantic):
        def input(self,obs,label,node,kind='tap',value=None,transition=None,popup=False,semantic_context=()):
            if label!=LABEL:
                return super().input(obs,label,node,kind,value,transition,popup,semantic_context)
            base.need(not getattr(self,'first_open_consumed',False),'FIRST_OPEN_NO_SECOND_DECISION')
            self.first_open_consumed=True
            base.need(kind=='tap' and value is None and not transition and not popup and not semantic_context
                and self.actions==1 and self.launches==1 and self.removals==0
                and len(self.owned)==1 and not self.pending,'FIRST_OPEN_ONLY_AFTER_SOLE_LAUNCH')
            focus=obs['focus'];shot=obs['screenshot'];scope=shot['scope']
            base.need(focus.get('package')==scope.get('package')==node.get('package')==PACKAGE
                and focus.get('activity')==scope.get('activity')==ACTIVITY
                and focus.get('task') in self.owned and focus.get('window_token')==scope.get('window_token')
                and node.get('class')=='android.widget.Button' and node.get('content-desc')=='New event'
                and node.get('text')=='' and node.get('resource-id')==''
                and node.get('visible') is True and node.get('enabled') is True and node.get('clickable') is True
                and node.get('editable') is False and node.get('password') is False
                and 16 in node.get('supported_actions',[]),'EXACT_OBSERVED_FIRST_NEW_EVENT_BUTTON_REQUIRED')
            self.box(obs,node)
            request={'package':PACKAGE,'display':0,'accessibility_mode':'none',
                'window_token':scope['window_token'],'frame_sha256':shot['frame_sha256'],
                'scope_sha256':shot['scope_sha256'],'context_token':shot['context_token']}
            base.need(len(obs['nodes'])==24,'FIRST_OPEN_OBSERVED_NODE_COUNT_CHANGED')
            previous=None;consecutive=0;settled=False
            for attempt in range(MAX_READS):
                step='read-'+str(attempt+1)
                self.check_tasks('snapshot-new-'+step)
                base.need(self.focus()==focus,'FIRST_OPEN_OWNED_FOCUS_CHANGED')
                frame=self.s.helper.capture(request)
                self.validate_text_window(shot,frame,label,'snapshot-new-'+step)
                self.s.helper.validate_snapshot(request,frame)
                fresh=self.s.helper.ui({'op':'dump','expected_package':PACKAGE,'display':0,'accessibility_mode':'none'})
                self.record(label+'-complete-native-'+step,fresh)
                if waitable_content_null(base,semantic,fresh,node,obs):
                    self.record(label+'-readiness-wait-'+step,{'observed_null_children':1,
                        'known_content_view_only_missing':True,'previous_consecutive_complete':consecutive,
                        'new_consecutive_complete':0,'input_dispatched':False,'maximum_readonly_samples':MAX_READS})
                    previous=None;consecutive=0
                    if attempt+1<MAX_READS:time.sleep(.15)
                    continue
                current=complete_target(base,semantic,fresh,node,obs)
                base.need(previous is None or current==previous,'FIRST_OPEN_TWO_COMPLETE_TREES_DIFFER')
                previous=current;consecutive+=1
                self.record(label+'-pixel-bound-'+step,{'complete_frame_sha256':frame['meta']['frame_sha256'],
                    'scope_sha256':frame['meta']['scope_sha256'],'both_hashes_equal_observation':True,
                    'context_token':frame['meta']['context_token'],'fixed_coordinates':False,'action_started':False})
                if consecutive==2:settled=True;break
            base.need(settled,'FIRST_OPEN_COMPLETE_READINESS_NOT_OBSERVED_WITHIN_BOUND')
            self.check_tasks('snapshot-new-final')
            base.need(self.focus()==focus,'FIRST_OPEN_LAST_OWNED_FOCUS_CHANGED')
            self.record(label+'-snapshot-branch',{'source':'unchanged_calendar_ui14.Adapter.input',
                'fresh_consecutive_complete_trees':2,'readonly_samples':attempt+1,'maximum_readonly_samples':MAX_READS,
                'full_frame_and_scope_hashes_required':True,
                'coordinates_from_current_node_bounds':True,'automatic_retry':False})
            # This unchanged implementation adds another exact snapshot validation
            # inside dispatch before its one input command; it retains all pending
            # and post-action observation rules. No semantic-click fallback exists.
            return original_pointer.input(self,obs,label,node,kind,value,transition,popup)
    return FirstOpenSnapshot

"""Narrow Calendar Button clicks using the installed v2 semantic action contract."""
LABELS={'New event','Create local calendar','Create','Cancel','Discard','Save','Edit','Delete'}
def without_connection_id(node):
    if not isinstance(node,dict) or type(node.get('window_id')) is not int or node['window_id']<0:
        raise RuntimeError('SEMANTIC_CONNECTION_ID_REQUIRED')
    return {key:value for key,value in node.items() if key!='window_id'}
def selector_for(node):
    return {'package':node['package'],'class':node['class'],'id':node['resource-id'],
        'text':node['text'],'desc':node['content-desc'],'enabled':True,'clickable':True}
def selector_matches(node,selector):
    aliases={'id':'resource-id','desc':'content-desc'}
    return all(node.get(aliases.get(key,key))==value for key,value in selector.items())
def extend(base):
    class CalendarSemanticButton(base.Adapter):
        def input(self,obs,label,node,kind='tap',value=None,transition=None,popup=False):
            semantic=(kind=='tap' and node.get('class')=='android.widget.Button'
                and (node.get('text') in LABELS or node.get('content-desc') in LABELS))
            if not semantic:
                return super().input(obs,label,node,kind,value,transition,popup)
            base.need(value is None and not transition and not popup,'SEMANTIC_BUTTON_SCOPE')
            self.budget();base.need(not self.pending,'PENDING_INPUT_NOT_REPLAYABLE')
            self.check_tasks('before-'+label);base.need(self.focus()==obs['focus'],'INPUT_FOCUS_CHANGED')
            shot=obs['screenshot'];scope=shot['scope']
            base.need(scope['package']==node.get('package')=='com.android.calendar'
                and node.get('visible') is True and node.get('enabled') is True
                and node.get('clickable') is True and node.get('editable') is False
                and node.get('password') is False,'VISIBLE_OWNED_NONEDITABLE_BUTTON_REQUIRED')
            self.box(obs,node)  # Retain full visible geometry within the owned scope.
            selector=selector_for(node)
            capture_request={'package':scope['package'],'display':0,'accessibility_mode':'none',
                'window_token':scope['window_token'],'context_token':shot['context_token']}
            first=self.s.helper.capture(capture_request)
            self.validate_text_window(shot,first,label,'button-first')
            fresh=self.s.helper.ui({'op':'dump','expected_package':scope['package'],
                'display':0,'accessibility_mode':'none'})
            self.record(label+'-semantic-fresh-native',fresh)
            base.need(fresh.get('ok') is True and fresh.get('outcome_unknown') is not True
                and fresh.get('accessibility_mode_restoration_verified') is True,'FRESH_NATIVE_NOT_VERIFIED')
            matches=[item for item in fresh.get('nodes',[]) if selector_matches(item,selector)]
            base.need(len(matches)==1 and without_connection_id(matches[0])==without_connection_id(node),
                'FULL_UNIQUE_BUTTON_NODE_CHANGED')
            last=self.s.helper.capture(capture_request)
            self.validate_text_window(shot,last,label,'button-last')
            self.check_tasks('last-'+label);base.need(self.focus()==obs['focus'],'LAST_INPUT_FOCUS_CHANGED')
            request={'op':'click','method':'accessibility','package':scope['package'],'display':0,
                'accessibility_mode':'none','window_token':scope['window_token'],'selector':selector}
            self.record(label+'-intent',{'request':request,'kind':'tap','node':node,'automatic_retry':False,
                'semantic_button':True,'native_action':'ACTION_CLICK','pointer_pixels_used':False})
            self.actions+=1;self.pending[label]={'input_acknowledged':False,'kind':'tap'}
            self.s.guard()
            try:reply=self.s.helper.dispatch(request)
            except BaseException as exc:
                details=getattr(exc,'details',{})
                if details.get('outcome_unknown') is not True and (details.get('action_taken') is False
                        or details.get('outcome_unknown') is False):
                    self.record(label+'-no-effect',{'error':str(exc),'details':details,'action_replayed':False})
                    del self.pending[label]
                raise
            self.s.guard();self.record(label+'-response',reply)
            base.need(reply.get('ok') is True and reply.get('performed')=='click'
                and reply.get('accessibility_mode_restoration_verified') is True
                and reply.get('visual_verified') is False and reply.get('business_success_verified') is False
                and (reply.get('outcome_unknown') is not True or reply.get('post_action_observation_available') is False),
                'SEMANTIC_BUTTON_OUTCOME_UNKNOWN_NO_REPLAY')
            base.need(without_connection_id(reply.get('target'))==without_connection_id(node)
                and reply.get('target')==reply.get('actual_target'),'SEMANTIC_BUTTON_ACTUAL_TARGET_CHANGED')
            self.pending[label].update(input_acknowledged=True,post_capture_outcome_unknown=reply.get('outcome_unknown') is True)
            return reply
    return CalendarSemanticButton

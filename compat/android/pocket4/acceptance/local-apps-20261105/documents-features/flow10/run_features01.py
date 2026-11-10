#!/usr/bin/python3 -I
"""First remaining Documents feature batch; default inert, one fresh owned tree."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,re,signal,time,types

ROOT=Path('/home/alex/work/pocket4-documents-features-flow-20261105-r12-10')
TOOLS=Path('/home/alex/work/pocket4-documents-features-tools-20261105-r12-10')
TRANSPORT=Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TRANSPORT_SHA='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
PINS={'features_ui.py': 'edaf39c50d6ff85748fef1b287bf3875fd51321a0a2a837ff6f30e59a8cd4417', 'package_fixture.py': '596dfb03273f2810cf9f98871668042bb62f85807d6cdad9a113b87003b8d932', 'owned_tree.py': 'e4b19adc1e47719413bfae5656bac8b04f5624c779ee7118b490327e2776a445', 'runtime_evidence.py': 'a8aa502e397187d0460c18efa1da09f46bafce9f019b1048046bfce8d2468c65', 'bounded_diagnostics.py': 'd3ab104ff92a942de1d45855ec3c8d44b742373ce67087e67773d15b46abf064'}
RUN='eeff7aa90e47139a';PACKAGE='org.droidloom.qa.documents.r12.n'+RUN
FOLDER='Pocket4_DocFeatures_r12_'+RUN;SOURCE='source-'+RUN;COPIES='copies-'+RUN
ALPHA='alpha-'+RUN+'.txt';BETA='beta-'+RUN+'.txt';APP_LABEL='Pocket4 Owned Documents eeff7aa9'
DOCS='com.android.documentsui';CLIENT=(PACKAGE,PACKAGE+'.FeaturesActivity')
FILES=(DOCS,DOCS+'.files.FilesActivity');PICKER=(DOCS,DOCS+'.picker.PickActivity')
PRIMARY_TITLE='Cuttlefish';PRIMARY_ROOT_FLAGS=1114139
MAX_SECONDS=900;CLEANUP_RESERVE=150
REQUIRED_GATES={'GET_CONTENT_CANCEL','TREE_CANCEL','EXACT_TREE_GRANT','FILES_NEW_FOLDER',
    'FILES_MULTIPLE_COPY','FILES_MULTIPLE_MOVE','FILES_MULTIPLE_DELETE_COPIES',
    'NORMAL_CLOSE_REOPEN_APP_READBACK','REVOKED_EXISTING_URI_SECURITY_DENIAL',
    'GET_CONTENT_EXACT_FILE_READ','FILES_UI_FINAL_DELETE','FINAL_GRANTS_EMPTY'}

def need(ok,why):
    if not ok:raise RuntimeError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stamp():return datetime.now(timezone.utc).isoformat()
def load(path,pin):
    raw=Path(path).read_bytes();need(sha(raw)==pin,'SOURCE_PIN_CHANGED:'+Path(path).name)
    value=types.ModuleType('features_'+Path(path).stem);value.__file__=str(path)
    exec(compile(raw,str(path),'exec'),value.__dict__);return value
def stable_node(node):return {k:v for k,v in node.items() if k!='window_id'}
def contains(outer,inner):
    return (isinstance(outer,list) and isinstance(inner,list) and len(outer)==len(inner)==4
        and all(type(x) is int for x in outer+inner)
        and outer[0]<=inner[0]<inner[2]<=outer[2] and outer[1]<=inner[1]<inner[3]<=outer[3])

class Flow:
    def __init__(self,s,tx,ui,pkg,tree,runtime,diag):
        self.s,self.tx,self.diag=s,tx,diag;self.ui=ui.Adapter(s,tx,ROOT/'ui')
        self.result={'schema':'pocket4-owned-documents-remaining-features-v1','state':'NOT_STARTED',
            'run':RUN,'temporary_package':PACKAGE,'started_utc':stamp(),'gates':{},'client_phases':[],
            'whole_app_production_ready':False,'business_scope_completed':False,'automatic_retry':False,
            'temporary_helper_excluded_from_launcher_denominator':True,'host_file_contents_written':False,
            'user_document_contents_read':False,'deferred_supported_features':['search','sort']}
        self.pkg=pkg.PackageFixture(s,tx,self.ui,self.result);self.tree=tree.OwnedTree(s,self.ui.record)
        self.runtime_type=runtime.RuntimeEvidence;self.runtime=None;self.operation_pending=None;self.helper_pending={}
        self.before_diag=None;self.before_permissions=None;self.before_packages=None;self.last_status=None

    def gate(self,label,proof):
        need(label in REQUIRED_GATES and label not in self.result['gates'],'DUPLICATE_OR_UNDECLARED_GATE')
        self.result['gates'][label]={'passed':True,**proof};self.ui.record('gate-'+label.lower().replace('_','-'),proof)

    def status(self,phase,obs=None):
        if obs is None:obs=self.ui.observe('client-'+phase.lower().replace('_','-'),[CLIENT])
        need((obs['focus']['package'],obs['focus']['activity'])==CLIENT,'CLIENT_ROUTE_REQUIRED')
        node=self.ui.one(obs,lambda n:n.get('resource-id')==PACKAGE+':id/status','ONE_CLIENT_STATUS')
        value=json.loads(node.get('text',''))
        need(value.get('run')==RUN and value.get('phase')==phase and value.get('pending')==''
            and value.get('step_pending')=='' and value.get('error')=='','CLIENT_PHASE_NOT_VERIFIED:'+phase)
        private=self.pkg.pref_state()
        need(private is not None and private.get('phase')==phase and private.get('pending','')==''
            and private.get('step_pending','')=='' and private.get('error','')=='','PRIVATE_PHASE_DIFFERS')
        for key in ('activity_creations','picker_calls','provider_create_calls','content_writes',
                    'content_readbacks','files_launch_calls','files_verify_calls','release_calls',
                    'denial_probes','security_denials_observed','get_content_results'):
            need(type(value.get(key)) is int and value[key]==private.get(key,0),'PRIVATE_COUNTER_DIFFERS:'+key)
        self.last_status=value;self.helper_pending={};self.result['client_phases'].append(value);return obs

    def private_completed(self,phase):
        value=self.pkg.pref_state()
        need(value is not None and value.get('phase')==phase and value.get('pending','')==''
            and value.get('step_pending','')=='' and value.get('error','')=='','HELPER_TRANSITION_NOT_COMPLETED')
        self.ui.record('helper-transition-completed',{'expected_phase':phase,'original':self.helper_pending,
            'provider_or_file_business_success_claimed':False})
        self.helper_pending={};return value

    def client(self,obs,suffix,label,transition=None):
        need(not self.helper_pending,'PREVIOUS_HELPER_ACTION_NOT_RESOLVED')
        node=self.ui.one(obs,lambda n:n.get('resource-id')==PACKAGE+':id/'+suffix
            and n.get('enabled') is True and n.get('clickable') is True,'ONE_ACTIVE_CLIENT_BUTTON')
        self.helper_pending={'client_action':label,'previous_phase':self.last_status['phase']}
        self.ui.record('helper-action-intent',{'pending':self.helper_pending,'automatic_retry':False})
        try:self.ui.input(obs,label,node,transition=transition)
        except BaseException as exc:
            details=getattr(exc,'details',{})
            if details.get('action_taken') is False and details.get('outcome_unknown') is not True and not self.ui.pending:
                self.helper_pending={}
            raise

    def control(self,obs,texts,button=False):
        if isinstance(texts,str):texts={texts}
        names={x.casefold() for x in texts}
        return self.ui.one(obs,lambda n:n.get('enabled') is True and n.get('editable') is False
            and n.get('class') in (('android.widget.Button','android.widget.ImageButton') if button else
                ('android.widget.TextView','android.widget.Button','android.widget.ImageButton','android.widget.CheckedTextView'))
            and (str(n.get('text','')).strip().casefold() in names
                or str(n.get('content-desc','')).strip().casefold() in names),'ONE_ACTUAL_CONTROL:'+','.join(sorted(texts)))

    def location(self,obs,relative=''):
        need(relative in ('',SOURCE,COPIES),'OWNED_DIRECTORY_ONLY')
        target=relative or FOLDER
        crumbs=[n for n in obs['nodes'] if n.get('resource-id')==DOCS+':id/breadcrumb_text']
        names=[n.get('text') for n in sorted(crumbs,key=lambda n:n['bounds_array'][0])]
        need(names and names[-1]==target and FOLDER in names,'OWNED_BREADCRUMB_REQUIRED:'+target)
        self.tree.guard();return crumbs

    def row(self,obs,name):
        need(name in {SOURCE,COPIES,ALPHA,BETA},'ONLY_FIXED_GENERATED_ROW')
        label=self.ui.one(obs,lambda n:n.get('text')==name and n.get('editable') is False,'ONE_OWNED_FILENAME:'+name)
        candidates=[n for n in obs['nodes'] if n.get('resource-id')==DOCS+':id/item_root'
            and n.get('enabled') is True and n.get('clickable') is True and 16 in n.get('supported_actions',[])
            and n.get('window_id')==label.get('window_id') and contains(n.get('bounds_array'),label.get('bounds_array'))]
        need(len(candidates)==1,'ONE_ACTUAL_FILE_ROW_CONTAINER');return candidates[0]

    def rows(self,obs,names,relative=''):
        self.location(obs,relative);names=set(names)
        need(names<=set((SOURCE,COPIES,ALPHA,BETA)),'ROW_SCOPE')
        actual=[n for n in obs['nodes'] if n.get('resource-id')==DOCS+':id/item_root']
        expected=[self.row(obs,name) for name in sorted(names)]
        need(len(actual)==len(expected) and all(n in expected for n in actual),'ONLY_EXACT_OWNED_ROWS_VISIBLE')
        return expected

    def more(self,obs,selected=0):
        need((obs['focus']['package'],obs['focus']['activity'])==FILES,'FILES_ROUTE_FOR_MENU')
        rid=DOCS+(':id/action_mode_bar' if selected else ':id/toolbar')
        bar=self.ui.one(obs,lambda n:n.get('resource-id')==rid and n.get('class')=='android.view.ViewGroup'
            and n.get('enabled') is True,'ONE_ACTUAL_FILES_BAR')
        if selected:self.ui.one(obs,lambda n:n.get('resource-id')==DOCS+':id/action_bar_title'
            and re.fullmatch(str(selected)+r'(?:\s+items?)?\s+selected',str(n.get('text','')).strip(),re.I)
            and contains(bar.get('bounds_array'),n.get('bounds_array')),'EXACT_SELECTED_COUNT')
        else:need(not any(n.get('resource-id')==DOCS+':id/action_mode_bar' for n in obs['nodes']),
            'UNEXPECTED_ACTIVE_SELECTION')
        return self.ui.one(obs,lambda n:n.get('class')=='android.widget.ImageView'
            and n.get('content-desc')=='More options' and n.get('clickable') is True
            and n.get('enabled') is True and 16 in n.get('supported_actions',[])
            and n.get('window_id')==bar.get('window_id') and contains(bar.get('bounds_array'),n.get('bounds_array')),
            'ONE_SOURCE_BOUND_OVERFLOW')

    def select(self,obs,relative,names,label):
        self.tree.expect(self.tree.expected,label+'-before-selection');self.rows(obs,names,relative)
        self.ui.input(obs,label+'-menu',self.more(obs),popup=True)
        menu=self.ui.observe(label+'-menu',[FILES]);self.tree.expect(self.tree.expected,label+'-selection-namespace')
        self.ui.input(menu,label+'-select-all',self.control(menu,'Select all'))
        selected=self.ui.observe(label+'-selected',[FILES]);rows=self.rows(selected,names,relative)
        need(all(row.get('selected') is True for row in rows),'OWNED_ROWS_NOT_ALL_SELECTED')
        self.more(selected,len(names))
        self.ui.record(label+'-selection-proof',{'relative':relative,'selected_names':sorted(names),
            'all_current_entries_are_generated':True,'count':len(names),'long_press_used':False})
        return selected

    def enter_directory(self,obs,name,label,routes=(FILES,)):
        need(name in (SOURCE,COPIES),'FIXED_DIRECTORY_ONLY');self.location(obs)
        self.tree.expect(self.tree.expected,label+'-namespace')
        self.ui.input(obs,label,self.row(obs,name));result=self.ui.observe(label+'-result',routes)
        self.location(result,name);return result

    def root_directory(self,obs,label,routes=(FILES,)):
        crumbs=[n for n in obs['nodes'] if n.get('resource-id')==DOCS+':id/breadcrumb_text']
        names=[n.get('text') for n in sorted(crumbs,key=lambda n:n['bounds_array'][0])]
        need(names and FOLDER in names and names[-1] in (FOLDER,SOURCE,COPIES),'CURRENT_LOCATION_NOT_OWNED_TREE')
        if names[-1]==FOLDER:self.location(obs);return obs
        # The real flow06 breadcrumb titles are disabled for ancestor entries.
        # Their enclosing enabled item is handled by the breadcrumb touch router;
        # requiring a clickable TextView can never match the saved source path.
        item=self.ui.one(obs,lambda n:n.get('resource-id')==DOCS+':id/breadcrumb_text'
            and n.get('text')==FOLDER and n.get('class')=='android.widget.TextView'
            and n.get('visible') is True,
            'ONE_ACTUAL_OWNED_ROOT_BREADCRUMB')
        bar=self.ui.one(obs,lambda n:n.get('resource-id')==DOCS+':id/horizontal_breadcrumb'
            and n.get('class')=='androidx.recyclerview.widget.RecyclerView'
            and n.get('enabled') is True,'ONE_ACTUAL_BREADCRUMB_BAR')
        node=self.ui.one(obs,lambda n:n.get('package')==DOCS and n.get('resource-id')==''
            and n.get('class')=='android.widget.LinearLayout' and n.get('enabled') is True
            and n.get('visible') is True and n.get('window_id')==item.get('window_id')==bar.get('window_id')
            and contains(bar.get('bounds_array'),n.get('bounds_array'))
            and contains(n.get('bounds_array'),item.get('bounds_array')),
            'ONE_ACTUAL_OWNED_BREADCRUMB_ITEM')
        b=node['bounds_array'];point=((b[0]+b[2])//2,(b[1]+b[3])//2);t=item['bounds_array']
        need(t[0]<=point[0]<t[2] and t[1]<=point[1]<t[3],'BREADCRUMB_TOUCH_OUTSIDE_OWNED_TITLE')
        self.tree.guard()
        self.ui.input(obs,label,node);out=self.ui.observe(label+'-result',routes);self.location(out);return out

    def primary_root_metadata(self,label):
        """Only the previously observed provider's root metadata; no file listing."""
        self.s.guard()
        raw=self.s.android(['/system/bin/content','query','--uri',
            'content://com.android.externalstorage.documents/root','--projection',
            'root_id:flags:title:document_id:available_bytes'],15).decode()
        self.s.guard()
        pattern=r'Row: 0 root_id=primary, flags=(\d+), title=Cuttlefish, document_id=primary:, available_bytes=(-?\d+)\n?'
        match=re.fullmatch(pattern,raw)
        need(match is not None and int(match[1])==PRIMARY_ROOT_FLAGS,'EXACT_PRIMARY_PROVIDER_ROOT_METADATA_REQUIRED')
        value={'authority':'com.android.externalstorage.documents','root_id':'primary',
            'document_id':'primary:','title':PRIMARY_TITLE,'flags':int(match[1]),
            'available_bytes':int(match[2]),'raw_sha256':sha(raw.encode()),
            'provider_uid':self.before_packages['com.android.externalstorage']['uid'],
            'provider_apk_sha256':self.before_packages['com.android.externalstorage']['apk_sha256'],
            'directory_entries_or_file_contents_queried':False}
        self.ui.record(label+'-primary-root-metadata',value);return value

    def destination_root(self,obs,label):
        """Navigate the existing copy/move picker; never write into its default root."""
        need((obs['focus']['package'],obs['focus']['activity'])==PICKER
            and not obs['focus'].get('popup'),'OWNED_DESTINATION_PICKER_REQUIRED')
        crumbs=[n for n in obs['nodes'] if n.get('resource-id')==DOCS+':id/breadcrumb_text']
        names=[n.get('text') for n in sorted(crumbs,key=lambda n:n['bounds_array'][0])]
        if FOLDER in names:return self.root_directory(obs,label,(PICKER,))
        need(names in (['Downloads'],[PRIMARY_TITLE]),'UNRECOGNIZED_DEFAULT_DESTINATION_PRESERVED')
        self.tree.expect(self.tree.expected,label+'-owned-namespace-before-navigation')
        root=self.primary_root_metadata(label)
        if names==['Downloads']:
            toolbar=self.ui.one(obs,lambda n:n.get('resource-id')==DOCS+':id/toolbar'
                and n.get('class')=='android.view.ViewGroup' and n.get('enabled') is True,
                'ONE_ACTUAL_DESTINATION_TOOLBAR')
            button=self.ui.one(obs,lambda n:n.get('class')=='android.widget.ImageButton'
                and n.get('content-desc')=='Show roots' and n.get('enabled') is True
                and n.get('clickable') is True and n.get('package')==DOCS
                and n.get('window_id')==toolbar.get('window_id')
                and contains(toolbar.get('bounds_array'),n.get('bounds_array')),
                'ONE_ACTUAL_SHOW_ROOTS')
            self.ui.input(obs,label+'-show-roots',button)
            drawer=self.ui.observe(label+'-roots',[PICKER])
            # Use the actual unique visible root title returned by the pinned
            # provider, inside the actual roots list rather than behind it.
            # No index, guessed position, URI grant or setting toggle.
            panel=self.ui.one(drawer,lambda n:n.get('package')==DOCS
                and n.get('resource-id')==DOCS+':id/container_roots'
                and n.get('enabled') is True and n.get('visible') is True,
                'ONE_ACTUAL_ROOTS_PANEL')
            roots=self.ui.one(drawer,lambda n:n.get('package')==DOCS
                and n.get('resource-id')==DOCS+':id/roots_list'
                and n.get('enabled') is True and n.get('visible') is True
                and n.get('window_id')==panel.get('window_id')
                and contains(panel.get('bounds_array'),n.get('bounds_array')),
                'ONE_ACTUAL_ROOTS_LIST')
            title=self.ui.one(drawer,lambda n:n.get('package')==DOCS
                and n.get('class')=='android.widget.TextView' and n.get('text')==root['title']
                and n.get('enabled') is True and n.get('visible') is True
                and n.get('editable') is False and n.get('window_id')==roots.get('window_id')
                and contains(roots.get('bounds_array'),n.get('bounds_array')),
                'ONE_ACTUAL_VERIFIED_PRIMARY_ROOT_TITLE')
            self.ui.input(drawer,label+'-select-primary',title)
            obs=self.ui.observe(label+'-primary-root',[PICKER])
        crumbs=[n for n in obs['nodes'] if n.get('resource-id')==DOCS+':id/breadcrumb_text']
        names=[n.get('text') for n in sorted(crumbs,key=lambda n:n['bounds_array'][0])]
        need(names==[root['title']],'PRIMARY_ROOT_NAVIGATION_NOT_VERIFIED')
        need(not any(n.get('resource-id')==DOCS+':id/roots_list'
            and n.get('visible') is True for n in obs['nodes']),'ROOTS_DRAWER_NOT_CLOSED')
        self.tree.guard()
        title=self.ui.one(obs,lambda n:n.get('package')==DOCS and n.get('text')==FOLDER
            and n.get('class')=='android.widget.TextView' and n.get('enabled') is True
            and n.get('visible') is True and n.get('editable') is False,
            'ONE_EXACT_OWNED_FOLDER_IN_PRIMARY_ROOT')
        row=self.ui.one(obs,lambda n:n.get('resource-id')==DOCS+':id/item_root'
            and n.get('package')==DOCS and n.get('enabled') is True and n.get('clickable') is True
            and 16 in n.get('supported_actions',[]) and n.get('window_id')==title.get('window_id')
            and contains(n.get('bounds_array'),title.get('bounds_array')),
            'ONE_EXACT_OWNED_FOLDER_CONTAINER')
        self.ui.input(obs,label+'-open-owned-folder',row)
        out=self.ui.observe(label+'-owned-root',[PICKER]);self.location(out)
        self.tree.expect(self.tree.expected,label+'-owned-namespace-after-navigation')
        self.ui.record(label+'-navigation-verified',{'root_id':root['root_id'],
            'authority':root['authority'],'owned_folder':FOLDER,'new_URI_grants':0,
            'file_operation_committed':False,'broader_location_accepted_for_writes':False})
        return out

    def begin_operation(self,label,expected):
        need(self.operation_pending is None and not self.ui.pending,'PREVIOUS_FILE_OPERATION_UNRESOLVED')
        self.tree.expect(self.tree.expected,label+'-before')
        self.operation_pending={'label':label,'before':sorted(self.tree.expected),'expected':sorted(expected),
            'input_replayed':False,'business_result_verified':False}
        self.ui.record(label+'-file-operation-intent',self.operation_pending)
        if self.runtime:self.runtime.phase_changed(label)

    def layout_result(self,expected,label):
        need(self.operation_pending is not None,'NO_RECORDED_FILE_OPERATION')
        deadline=time.monotonic()+35;last=None
        while True:
            try:proof=self.tree.expect(expected,label+'-readback',True);break
            except (FileNotFoundError,RuntimeError) as exc:
                last=type(exc).__name__+': '+str(exc)
                transient=isinstance(exc,FileNotFoundError) or str(exc).startswith((
                    'EXACT_GENERATED_LAYOUT_REQUIRED:','FIXTURE_FILE_TYPE_SIZE_OR_LINKS',
                    'FIXTURE_FILE_CHANGED_OR_HASH_MISMATCH','ROOT_ENTRIES_CHANGED_DURING_READ',
                    'CHILD_ENTRIES_CHANGED_DURING_READ'))
                need(transient and time.monotonic()<deadline,'FILE_OPERATION_UNRESOLVED_PRESERVE:'+last)
                time.sleep(.2)
        original=self.operation_pending
        self.ui.record(label+'-file-operation-completed',{'original_intent':original,'readback':proof,
            'input_ack_is_not_business_evidence':True,'last_transient_observation':last})
        self.operation_pending=None;return proof

    def dialog_confirm(self,obs,label,expected_text,positive):
        def controls(value):
            field=self.ui.one(value,lambda n:n.get('editable') is True and n.get('text')==expected_text,
                'EXACT_DIALOG_EDITOR_TEXT') if expected_text is not None else None
            button=self.ui.one(value,lambda n:n.get('resource-id')=='android:id/button1'
                and n.get('class')=='android.widget.Button' and n.get('enabled') is True
                and n.get('clickable') is True and str(n.get('text','')).strip().casefold() in positive,
                'ONE_DIALOG_POSITIVE_CONTROL')
            return field,button
        field,button=controls(obs);focus=obs['focus'];context=obs['screenshot']['context_token']
        for decision in range(3):
            try:self.ui.input(obs,label+'-'+str(decision+1),button);return
            except self.s.helper.ControlError as exc:
                details=exc.details
                if (str(exc)!='STALE_FRAME' or details.get('action_taken') is not False
                    or details.get('outcome_unknown') is True or self.ui.pending or decision==2):raise
                fresh=self.ui.observe(label+'-fresh-'+str(decision+2),[FILES])
                need(fresh['focus']==focus and fresh['screenshot']['context_token']==context,'DIALOG_CONTEXT_CHANGED')
                newfield,newbutton=controls(fresh)
                need(stable_node(newbutton)==stable_node(button) and
                    (field is None and newfield is None or field is not None and stable_node(newfield)==stable_node(field)),
                    'DIALOG_FORM_CHANGED_AFTER_EXPLICIT_NO_EFFECT')
                self.ui.record('explicit-no-effect-new-decision',{'action_taken':False,
                    'previous_label':label+'-'+str(decision+1),'maximum_decisions':3,'unknown_input_replayed':False})
                obs,field,button=fresh,newfield,newbutton

    def cancel_picker(self,obs,phase,label):
        self.location(obs);need(self.tree.expected==set(),'CANCEL_PRECONDITION_EMPTY_ROOT')
        for index in range(3):
            need((obs['focus']['package'],obs['focus']['activity'])==PICKER,'CANCEL_ONLY_OWNED_PICKER')
            cancel=[n for n in obs['nodes'] if n.get('enabled') is True and n.get('clickable') is True
                and n.get('editable') is False and n.get('class') in ('android.widget.Button','android.widget.ImageButton')
                and (str(n.get('text','')).strip().casefold()=='cancel' or n.get('content-desc')=='Cancel')]
            if len(cancel)==1:self.ui.input(obs,label+'-cancel-'+str(index),cancel[0])
            else:need(not cancel,'CANCEL_CONTROL_AMBIGUOUS');self.ui.back(obs,label+'-back-'+str(index))
            obs=self.ui.observe(label+'-result-'+str(index),[PICKER,CLIENT])
            if (obs['focus']['package'],obs['focus']['activity'])==CLIENT:break
        obs=self.status(phase,obs);self.tree.expect(set(),label+'-still-empty')
        self.pkg.grants(label+'-no-uri-grants',True);return obs

    def new_folder_name_input(self,dialog,title,field):
        need(field.get('resource-id')=='android:id/text1' and field.get('class')=='android.widget.EditText'
            and field.get('text')==field.get('hint')=='Name' and field.get('value')==''
            and field.get('showing-hint') is True,'ACTUAL_EMPTY_NEW_FOLDER_FIELD_REQUIRED')
        self.ui.input(dialog,'new-folder-name',field,'set-text',COPIES,semantic_context=(title,))

    def new_folder(self,obs):
        self.location(obs);self.rows(obs,{SOURCE})
        self.ui.input(obs,'new-folder-menu',self.more(obs),popup=True)
        menu=self.ui.observe('new-folder-menu',[FILES])
        self.ui.input(menu,'new-folder-dialog',self.control(menu,'New folder'))
        dialog=self.ui.observe('new-folder-dialog',[FILES])
        title=self.ui.one(dialog,lambda n:n.get('resource-id')==DOCS+':id/alertTitle'
            and n.get('class')=='android.widget.TextView' and n.get('editable') is False
            and n.get('enabled') is True and n.get('text')=='New folder','ACTUAL_NEW_FOLDER_DIALOG_TITLE')
        field=self.ui.one(dialog,lambda n:n.get('editable') is True and n.get('enabled') is True
            and n.get('password') is False,'ONE_ACTUAL_NEW_FOLDER_EDITOR')
        self.new_folder_name_input(dialog,title,field)
        dialog=self.ui.observe('new-folder-name-readback',[FILES]);expected=self.tree.expected|{COPIES}
        self.begin_operation('new-folder',expected)
        self.dialog_confirm(dialog,'new-folder-confirm',COPIES,{'ok','create'})
        obs=self.ui.observe('new-folder-result',[FILES]);proof=self.layout_result(expected,'new-folder')
        self.rows(obs,{SOURCE,COPIES});self.gate('FILES_NEW_FOLDER',{'app_ui_created_directory':COPIES,'layout':proof})
        return obs

    def completed_operation_observation(self,obs,relative,names,label):
        # Actual08 reused the copy-result frame after its file readback. The
        # next pre-input capture differed only where "Copying 2 items." faded.
        # Resolve this phase boundary with reads, leaving every pointer digest
        # check and all unknown-input handling in Adapter.input unchanged.
        need(self.operation_pending is None and not self.ui.pending and not self.helper_pending,
            'OPERATION_OR_INPUT_PENDING_NO_NEW_OBSERVATION_DECISION')
        self.location(obs,relative);anchor=stable_node(self.more(obs))
        original=obs['screenshot'];focus=obs['focus'];previous=None
        end=time.monotonic()+12
        for index in range(4):
            need(time.monotonic()<end,'COMPLETED_OPERATION_VIEW_DID_NOT_SETTLE')
            self.ui.budget();fresh=self.ui.observe(label+'-settled-'+str(index+1),[FILES])
            shot=fresh['screenshot']
            need(fresh['focus']==focus,'COMPLETED_OPERATION_FOCUS_CHANGED')
            for scope in (original['scope'],shot['scope']):
                need(scope.get('a11y_window_id_is_connection_scoped') is True
                    and type(scope.get('window_id')) is int and scope['window_id']>=0,
                    'COMPLETED_OPERATION_CONNECTION_SCOPE_REQUIRED')
            need({k:v for k,v in original['scope'].items() if k!='window_id'}
                =={k:v for k,v in shot['scope'].items() if k!='window_id'},
                'COMPLETED_OPERATION_WINDOW_CHANGED')
            keys=('source','context_token','width','height','scope_bounds','scope_width',
                'scope_height','coordinate_space')
            need(all(shot[k]==original[k] for k in keys),'COMPLETED_OPERATION_GEOMETRY_CHANGED')
            self.rows(fresh,names,relative)
            need(stable_node(self.more(fresh))==anchor,'COMPLETED_OPERATION_CONTROL_CHANGED')
            self.tree.expect(self.tree.expected,label+'-settled-namespace-'+str(index+1))
            transient=[n for n in fresh['nodes'] if n.get('resource-id')==DOCS+':id/snackbar_text']
            self.ui.record(label+'-settled-readback',{'observation_index':index+1,
                'frame_sha256':shot['frame_sha256'],'scope_sha256':shot['scope_sha256'],
                'transient_texts':[n.get('text') for n in transient],
                'file_effect_already_verified':True,'UI_input_sent':False,
                'prior_input_replayed':False})
            need(time.monotonic()<end,'COMPLETED_OPERATION_VIEW_DID_NOT_SETTLE')
            if transient:previous=None
            elif previous is not None and all(shot[k]==previous[k]
                for k in ('frame_sha256','scope_sha256')):
                return fresh
            else:previous=shot
        raise RuntimeError('COMPLETED_OPERATION_VIEW_DID_NOT_SETTLE')

    def copy_or_move(self,obs,move=False):
        label='move' if move else 'copy';obs=self.select(obs,SOURCE,{ALPHA,BETA},label)
        self.ui.input(obs,label+'-menu',self.more(obs,2),popup=True)
        menu=self.ui.observe(label+'-menu',[FILES])
        texts={'Move to…','Move to...','Move to'} if move else {'Copy to…','Copy to...','Copy to'}
        self.ui.input(menu,label+'-destination-picker',self.control(menu,texts),transition=PICKER)
        picker=self.ui.observe(label+'-destination-picker',[PICKER],admit=True)
        picker=self.destination_root(picker,label+'-destination-root')
        if not move:picker=self.enter_directory(picker,COPIES,label+'-destination-copies',(PICKER,))
        self.location(picker,'' if move else COPIES)
        expected=(self.tree.expected-{SOURCE+'/'+ALPHA,SOURCE+'/'+BETA})|{ALPHA,BETA} if move else (
            self.tree.expected|{COPIES+'/'+ALPHA,COPIES+'/'+BETA})
        button=self.control(picker,{'Move','Move here'} if move else {'Copy','Copy here'},True)
        self.begin_operation(label,expected);self.ui.input(picker,label+'-confirm',button)
        obs=self.ui.observe(label+'-result',[FILES]);proof=self.layout_result(expected,label)
        self.location(obs,SOURCE)
        self.gate('FILES_MULTIPLE_MOVE' if move else 'FILES_MULTIPLE_COPY',{'files':[ALPHA,BETA],
            'source':SOURCE,'destination':'' if move else COPIES,'layout':proof,'operation_replayed':False})
        return self.completed_operation_observation(obs,SOURCE,set() if move else {ALPHA,BETA},label)

    def delete_confirmation(self,obs,count):
        # Real flow09 is an Appcompat confirmation with a framework OK button.
        # Bind title, exact plural count/message, panel and one window together;
        # an arbitrary OK button is never a deletion confirmation.
        need((obs['focus']['package'],obs['focus']['activity'])==FILES and count in (2,4),
            'OWNED_FILES_DELETE_DIALOG_SCOPE')
        def exact(rid,klass,text):
            return self.ui.one(obs,lambda n:n.get('package')==DOCS and n.get('resource-id')==rid
                and n.get('class')==klass and n.get('text')==text and n.get('visible') is True
                and n.get('enabled') is True and n.get('editable') is False,
                'EXACT_DELETE_DIALOG_CONTROL:'+rid)
        title=exact(DOCS+':id/alertTitle','android.widget.TextView','Delete forever?')
        message=exact('android:id/message','android.widget.TextView',
            str(count)+' items will be deleted forever. This can’t be undone.')
        button=exact('android:id/button1','android.widget.Button','OK')
        cancel=exact('android:id/button2','android.widget.Button','CANCEL')
        panel=self.ui.one(obs,lambda n:n.get('package')==DOCS
            and n.get('resource-id')==DOCS+':id/buttonPanel' and n.get('visible') is True
            and n.get('enabled') is True,'ONE_ACTUAL_DELETE_BUTTON_PANEL')
        need(len({n.get('window_id') for n in (title,message,button,cancel,panel)})==1
            and type(button.get('window_id')) is int
            and button.get('clickable') is True and cancel.get('clickable') is True
            and 16 in button.get('supported_actions',[]) and 16 in cancel.get('supported_actions',[])
            and contains(panel.get('bounds_array'),button.get('bounds_array'))
            and contains(panel.get('bounds_array'),cancel.get('bounds_array')),
            'DELETE_DIALOG_WINDOW_OR_BUTTON_SCOPE_CHANGED')
        return button

    def delete_entries(self,obs,relative,names,gate,label):
        obs=self.select(obs,relative,set(names),label)
        bar=self.ui.one(obs,lambda n:n.get('resource-id')==DOCS+':id/action_mode_bar','DELETE_ACTION_MODE_BAR')
        delete=self.ui.one(obs,lambda n:n.get('resource-id')==DOCS+':id/action_menu_delete'
            and n.get('content-desc')=='Delete forever' and n.get('enabled') is True
            and n.get('clickable') is True and contains(bar.get('bounds_array'),n.get('bounds_array')),
            'ACTUAL_DELETE_FOREVER_SELECTED_CONTROL')
        removed={(relative+'/' if relative else '')+name for name in names}
        expected=self.tree.expected-removed
        need(not any(any(x.startswith(name+'/') for x in expected) for name in removed),
            'UI_DIRECTORY_DELETE_ONLY_WHEN_KNOWN_EMPTY')
        self.begin_operation(label,expected);self.ui.input(obs,label+'-request',delete)
        obs=self.ui.observe(label+'-dialog-or-result',[FILES])
        confirm=self.delete_confirmation(obs,len(names))
        self.tree.expect(self.tree.expected,label+'-before-confirm')
        self.ui.input(obs,label+'-confirm',confirm)
        obs=self.ui.observe(label+'-after-confirm',[FILES])
        proof=self.layout_result(expected,label);self.location(obs,relative)
        self.gate(gate,{'deleted_entries':sorted(removed),'physical_absence_and_remaining_hashes':proof,
            'all_selected_entries_preverified_owned':True,'host_unlink_used_for_gate':False})
        return obs

    def business(self):
        self.result['initial_guard']=self.s.guard()
        roots,tasks=self.ui.stacks('session-baseline-before-install')
        need(not any(c['component'].split('/')[0] in (PACKAGE,DOCS) for r in roots.values() for c in r['children']),
            'PREEXISTING_DOCUMENTS_OR_HELPER_TASK_PRESERVED')
        self.ui.baseline=tasks;self.result['baseline_task_ids']=sorted(tasks)
        self.before_packages=self.pkg.packages('target-packages-before')
        self.diag.uid_census(self.s,self.ui.record,'target-uid-census-before')
        self.before_permissions=self.diag.permissions(self.s,self.ui.record,'target-permissions-before')
        self.before_diag=self.diag.capture(self.s,self.ui.record,'diagnostics-before')
        self.pkg.install();self.tree.setup();self.tree.expect(set(),'initial-generated-root-empty')
        self.pkg.grants('initial-helper-grants-empty',True)
        self.runtime=self.runtime_type(self.s,self.tx,ROOT/'runtime',FOLDER);self.runtime.start()
        self.ui.launch();obs=self.status('NEW')
        self.client(obs,'cancel_get','request-get-cancel');picker=self.ui.observe('get-cancel-picker',[PICKER])
        obs=self.cancel_picker(picker,'GET_CANCELLED','get-cancel')
        need(self.last_status['get_cancel_results']==1,'GET_CANCEL_RESULT_COUNT')
        self.gate('GET_CONTENT_CANCEL',{'RESULT_CANCELED':True,'URI_returned':False,'grants_empty':True})
        self.client(obs,'cancel_tree','request-tree-cancel');picker=self.ui.observe('tree-cancel-picker',[PICKER])
        obs=self.cancel_picker(picker,'TREE_CANCELLED','tree-cancel')
        need(self.last_status['tree_cancel_results']==1,'TREE_CANCEL_RESULT_COUNT')
        self.gate('TREE_CANCEL',{'RESULT_CANCELED':True,'URI_returned':False,'grants_empty':True})
        self.client(obs,'grant_tree','request-tree-grant');picker=self.ui.observe('tree-grant-picker',[PICKER]);self.location(picker)
        self.ui.input(picker,'select-only-owned-tree',self.control(picker,{'Use this folder','Select'},True))
        obs=self.ui.observe('tree-grant-confirmation-or-result',[PICKER,CLIENT])
        if (obs['focus']['package'],obs['focus']['activity'])==PICKER:
            texts=[str(n.get('text','')) for n in obs['nodes'] if n.get('class')=='android.widget.TextView'
                and n.get('editable') is False]
            need(any(FOLDER in text for text in texts) and any(APP_LABEL in text for text in texts),
                'EXACT_APP_AND_GENERATED_TREE_CONSENT_REQUIRED')
            self.ui.input(obs,'allow-only-owned-tree',self.control(obs,'Allow',True));obs=self.ui.observe('tree-granted',[CLIENT])
        obs=self.status('TREE_GRANTED',obs)
        need(self.last_status['persisted_grant_count']==self.last_status['persist_calls']==self.last_status['tree_grant_results']==1,
            'EXACT_SINGLE_TREE_GRANT_COUNTERS')
        self.tree.expect(set(),'tree-grant-still-empty');self.pkg.grants('exact-owned-tree-grant')
        self.gate('EXACT_TREE_GRANT',{'tree':'primary:'+FOLDER,'persisted_read_write_grants':1,'broader_root_granted':False})
        self.runtime.phase_changed('seed');self.client(obs,'seed','seed-two-owned-fixtures');obs=self.status('SEEDED')
        need(self.last_status['provider_create_calls']==3 and self.last_status['content_writes']==2
            and self.last_status['content_readbacks']==2,'EXACT_TWO_FILE_SETUP_COUNTERS')
        self.tree.expect({SOURCE,SOURCE+'/'+ALPHA,SOURCE+'/'+BETA},'helper-fixture-setup-readback',True)
        self.result['fixture_setup']={'provider_directory_creates':1,'provider_file_creates':2,
            'content_writes':2,'App_UI_creation_credit':False,'file_bytes':[59,118]}
        self.client(obs,'files','open-files',FILES);obs=self.ui.observe('files-owned-root',[FILES],admit=True)
        self.private_completed('FILES_OPENED')
        obs=self.new_folder(obs);obs=self.enter_directory(obs,SOURCE,'open-owned-source')
        obs=self.copy_or_move(obs);obs=self.copy_or_move(obs,True)
        obs=self.root_directory(obs,'after-move-root');obs=self.enter_directory(obs,COPIES,'open-owned-copies')
        obs=self.delete_entries(obs,COPIES,{ALPHA,BETA},'FILES_MULTIPLE_DELETE_COPIES','delete-copies')
        self.ui.close_all();self.ui.launch();obs=self.status('FILES_OPENED')
        self.client(obs,'verify_files','verify-after-normal-reopen');obs=self.status('FILES_VERIFIED')
        need(self.last_status['content_readbacks']==4,'TWO_APP_HASH_READBACKS_AFTER_REOPEN')
        self.tree.expect({SOURCE,COPIES,ALPHA,BETA},'reopened-layout-and-content')
        self.gate('NORMAL_CLOSE_REOPEN_APP_READBACK',{'expected_payloads_verified_by_app':2,
            'same_generated_tree':True,'content_readbacks_total':4})
        self.client(obs,'release_tree','release-exact-tree');self.status('TREE_RELEASED')
        self.ui.close_all();self.ui.launch();obs=self.status('TREE_RELEASED')
        self.pkg.grants('released-grants-after-normal-reopen',True)
        self.tree.expect({SOURCE,COPIES,ALPHA,BETA},'denial-probe-target-still-exists')
        self.client(obs,'probe_revoked','probe-revoked-existing-file');obs=self.status('DENIED_OBSERVED')
        need(self.last_status['security_denials_observed']==self.last_status['denial_probes']==1
            and self.last_status['persisted_grant_count']==0,'ONE_REAL_SECURITY_DENIAL_REQUIRED')
        self.gate('REVOKED_EXISTING_URI_SECURITY_DENIAL',{'existing_file':BETA,'exception':'SecurityException',
            'persisted_grants_empty':True,'checked_before_any_GET_CONTENT_grant':True})
        self.client(obs,'get_content','get-owned-alpha');picker=self.ui.observe('get-owned-alpha-picker',[PICKER]);self.location(picker)
        self.tree.expect({SOURCE,COPIES,ALPHA,BETA},'before-get-exact-alpha')
        self.ui.input(picker,'select-get-content-alpha',self.row(picker,ALPHA));obs=self.status('GET_CONTENT_OK')
        need(self.last_status['get_content_results']==1 and self.last_status['last_read_bytes']==59
            and self.last_status['last_read_sha256']=='5cffe960dad99f99bdc3aeace1389e7a67a03e478c17bf92e689999a7fc8ffe1'
            and self.last_status['persisted_grant_count']==0,'EXACT_GET_CONTENT_READBACK')
        self.gate('GET_CONTENT_EXACT_FILE_READ',{'file':ALPHA,'bytes':59,'sha256':self.last_status['last_read_sha256'],
            'persisted_grants':0,'previous_tree_grant_absent':True})
        self.client(obs,'cleanup_files','open-files-cleanup',FILES)
        obs=self.ui.observe('files-final-owned-root',[FILES],admit=True)
        self.private_completed('FILES_CLEANUP_OPENED')
        self.delete_entries(obs,'',{SOURCE,COPIES,ALPHA,BETA},'FILES_UI_FINAL_DELETE','delete-final')
        self.ui.close_all();self.tree.expect(set(),'ui-delete-final-root-empty')
        self.pkg.grants('final-helper-grants-empty',True)
        private=self.pkg.pref_state()
        expected_counts={'picker_calls':4,'get_cancel_results':1,'tree_cancel_results':1,'tree_grant_results':1,
            'persist_calls':1,'seed_calls':1,'provider_create_calls':3,'content_writes':2,'content_readbacks':5,
            'files_launch_calls':2,'files_verify_calls':1,'release_calls':1,'release_mutations':1,
            'denial_probes':1,'security_denials_observed':1,'get_content_results':1}
        need(private is not None and private.get('phase')=='FILES_CLEANUP_OPENED'
            and private.get('pending','')==private.get('step_pending','')==''
            and all(private.get(k)==v for k,v in expected_counts.items()),'EXACT_FINAL_HELPER_PROTOCOL_COUNTS')
        self.result['final_helper_counters']={k:private[k] for k in expected_counts}
        self.gate('FINAL_GRANTS_EMPTY',{'all_owned_tasks_normally_closed':True,'URI_permission_section_empty':True})
        need(self.ui.launches==3 and self.ui.removals==len(self.ui.closed)==self.ui.launches+len(self.ui.adopted)
            and not self.ui.pending and not self.ui.owned and self.operation_pending is None,'LIFECYCLE_NOT_COMPLETE')
        need(set(self.result['gates'])==REQUIRED_GATES,'REQUIRED_BUSINESS_GATES_INCOMPLETE')
        self.result.update(state='SCOPED_DOCUMENTS_FEATURES_COMPLETED',business_scope_completed=True)

    def cleanup(self):
        out={'errors':[],'file_cleanup':None,'package':None,'stage':None,'runtime':None}
        if self.result.get('staging_setup_incomplete'):out['errors'].append('incomplete-staging-setup-preserved')
        try:self.ui.close_all()
        except BaseException as exc:out['errors'].append('owned-tasks:'+type(exc).__name__+':'+str(exc))
        if self.runtime:
            try:out['runtime']=self.runtime.stop()
            except BaseException as exc:out['errors'].append('runtime-reader:'+type(exc).__name__+':'+str(exc))
        try:
            need(not self.ui.pending and not self.ui.owned and self.operation_pending is None
                and not self.pkg.install_pending and not self.pkg.uninstall_pending,'UNKNOWN_EFFECT_PRESERVE_TREE_AND_PACKAGE')
            if self.pkg.installed is not None:
                try:phase=self.pkg.pref_state()
                except BaseException as exc:
                    self.helper_pending['phase_unreadable']=type(exc).__name__+':'+str(exc);raise
                # Empty old preferences cannot cancel the controller's intent:
                # an acknowledged input may still be queued before App begin().
                if phase is not None:self.helper_pending.update({k:phase[k] for k in ('pending','step_pending') if phase.get(k)})
                need(not self.helper_pending and (phase is None or phase.get('pending','')==phase.get('step_pending','')==''),
                    'HELPER_OPERATION_PENDING_PRESERVE_TREE_AND_PACKAGE')
                if self.tree.created:out['file_cleanup']=self.tree.remove_known(True)
            out['package']=self.pkg.uninstall(True)
        except BaseException as exc:out['errors'].append('fixture-or-package:'+type(exc).__name__+':'+str(exc))
        try:out['stage']=self.pkg.cleanup_staged()
        except BaseException as exc:out['errors'].append('staged-input:'+type(exc).__name__+':'+str(exc))
        self.tree.close();return out

    def final_checks(self):
        _,tasks=self.ui.check_tasks('final-task-set')
        self.result['task_set_restored']=not self.ui.owned and tasks==self.ui.baseline
        need(self.result['task_set_restored'],'FINAL_TASK_SET_NOT_RESTORED')
        self.diag.uid_census(self.s,self.ui.record,'target-uid-census-after')
        need(self.pkg.packages('target-packages-after')==self.before_packages,'TARGET_PACKAGE_IDENTITY_CHANGED')
        need(self.diag.permissions(self.s,self.ui.record,'target-permissions-after')==self.before_permissions,
            'TARGET_PERMISSION_STATE_CHANGED')
        if self.before_diag is not None:
            after=self.diag.capture(self.s,self.ui.record,'diagnostics-after')
            self.result['diagnostics']=self.diag.compare(self.before_diag,after)
            need(self.result['diagnostics']['no_new_crash_or_anr_observed'],'NEW_TARGET_CRASH_OR_ANR')
        self.result['final_guard']=self.s.guard()
        need(self.result['final_guard']==self.result['initial_guard'],'MAIN_GENERATION_CHANGED')

class Deadline(BaseException):pass
def expired(signum,frame):raise Deadline('DOCUMENTS_FEATURES_DEADLINE_NO_REPLAY')

def execute():
    need(set(PINS)=={'features_ui.py','package_fixture.py','owned_tree.py','runtime_evidence.py','bounded_diagnostics.py'},
        'REVIEWED_BUNDLE_NOT_FROZEN')
    tx=load(TRANSPORT,TRANSPORT_SHA);mods={k:load(TOOLS/k,v) for k,v in PINS.items()}
    result={'state':'FAILED_BEFORE_SESSION','business_scope_completed':False,'whole_app_production_ready':False}
    flow=None;started=time.monotonic();old=signal.signal(signal.SIGALRM,expired)
    try:
        with tx.ui_lock():
            ROOT.mkdir(mode=0o700);(ROOT/'ui').mkdir(mode=0o700)
            signal.setitimer(signal.ITIMER_REAL,MAX_SECONDS-CLEANUP_RESERVE)
            with tx.CameraSession(ROOT/'commands') as session:
                flow=Flow(session,tx,mods['features_ui.py'],mods['package_fixture.py'],mods['owned_tree.py'],
                    mods['runtime_evidence.py'],mods['bounded_diagnostics.py']);result=flow.result
                try:flow.business()
                except BaseException as exc:result.update(state='FEATURE_FLOW_STOPPED',business_scope_completed=False,
                    error=type(exc).__name__+': '+str(exc))
                finally:
                    signal.setitimer(signal.ITIMER_REAL,max(.001,min(CLEANUP_RESERVE,MAX_SECONDS-(time.monotonic()-started))))
                    result['cleanup']=flow.cleanup()
                    try:flow.final_checks();session.caller_status('documents-features-final-caller')
                    except BaseException as exc:result.update(state='FINAL_EVIDENCE_UNVERIFIED',business_scope_completed=False,
                        final_check_error=type(exc).__name__+': '+str(exc))
                    if (result['cleanup']['errors'] or not result['cleanup']['package']
                        or not result['cleanup']['package'].get('package_absent_verified')):
                        result.update(state='OWNED_CLEANUP_UNVERIFIED',business_scope_completed=False)
                    if result.get('business_scope_completed'):
                        need(result['cleanup']['file_cleanup']['removed'] is True
                            and result['cleanup']['file_cleanup']['fallback_files_unlinked']==0
                            and result['cleanup']['stage'].get('staged_apk_removed') is True,
                            'BUSINESS_SUCCESS_REQUIRES_TRUE_UI_DELETE_AND_COMPLETE_CLEANUP')
    except BaseException as exc:result.update(state='FEATURE_FLOW_STOPPED',business_scope_completed=False,
        outer_error=type(exc).__name__+': '+str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
        if flow is not None:
            result.update(ui_actions=flow.ui.actions,native_launch_calls=flow.ui.launches,
                owned_remove_calls=flow.ui.removals,owned_task_ids_closed=flow.ui.closed,
                source_bound_adopted_tasks=flow.ui.adopted,owned_tasks=flow.ui.owned,ui_pending=flow.ui.pending,
                file_operation_pending=flow.operation_pending,helper_pending=flow.helper_pending,install_pending=flow.pkg.install_pending,
                uninstall_pending=flow.pkg.uninstall_pending,
                outcome_unknown=bool(flow.ui.pending or flow.operation_pending or flow.helper_pending
                    or flow.pkg.install_pending or flow.pkg.uninstall_pending))
        result.update(finished_utc=stamp(),elapsed_seconds=time.monotonic()-started)
        if ROOT.is_dir():tx.write_new(ROOT/'result.json',result)
    print(json.dumps(result,indent=2,sort_keys=True));return 0 if result.get('business_scope_completed') else 1

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    if not args.execute:
        print(json.dumps({'state':'PLAN_ONLY','package':PACKAGE,'max_seconds':MAX_SECONDS,'max_ui_actions':80,
            'installs':0,'Android_actions':0,'provider_writes':0,'UI_actions':0,
            'required_business_gates':sorted(REQUIRED_GATES),'deferred_supported_features':['search','sort']}));return 0
    return execute()

if __name__=='__main__':raise SystemExit(main())

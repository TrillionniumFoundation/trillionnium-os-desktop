#!/usr/bin/env python3
"""Add lifecycle ownership to the exact installed six-class Editor preimage.

This is a bytecode-source patch, not a claim to have recovered the original Java.
All old method bodies are retained verbatim, either in place or behind an owner
wrapper. It never rebuilds the manifest/resources or uses another signing key.
"""
from pathlib import Path
import argparse
import difflib
import hashlib
import json
import re
import shutil

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'qa-fixtures08/disassembled03/org.droidloom.qa.editorcontract/smali'
M = 'Lorg/droidloom/qa/editorcontract/EditorContractActivity;'
E = 'Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText;'
W = 'Lorg/droidloom/qa/editorcontract/EditorContractActivity$ContractEditText$1;'
L = 'Lorg/droidloom/qa/editorcontract/SessionOwner;'
S = 'Lorg/droidloom/qa/editorcontract/RetainedEditorState;'
REL = 'org/droidloom/qa/editorcontract/'
PINS = {
    'EditorContractActivity.smali': 'efcec9c8801a4a43c7141b174a9adbe3db3fea45beed96357d447d1027e74e89',
    'EditorContractActivity$0.smali': 'd7eec314c39bc846e0405300cb64ee76bc0e2e459d58c75b562895886d8a25b4',
    'EditorContractActivity$1.smali': '4104858f7eebf059fe374021a8ff62b86d160831719395fc2e738befe5d72459',
    'EditorContractActivity$2.smali': '5c57239b1795bad8b3e21b369d7331f5febfcf569eb87c5144a266251b1b874b',
    'EditorContractActivity$ContractEditText.smali': 'b2810b530d560dd41cdd03f3cf327b161e8bbeb5d9ad8a3923012566dfb9b0de',
    'EditorContractActivity$ContractEditText$1.smali': 'b023ea58c707eb7537775c3eb8b8e5cc26ef93a372a9cfb9da7fa7ec1f0109a0',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def replace_one(text, before, after):
    if text.count(before) != 1:
        raise RuntimeError('EXACT_PREIMAGE_HUNK_REQUIRED:' + before[:100])
    return text.replace(before, after, 1)


def method(text, signature):
    match = re.search(r'^\.method [^\n]*\b' + re.escape(signature) + r'\n.*?^\.end method\n', text, re.M | re.S)
    if match is None:
        raise RuntimeError('EXACT_METHOD_REQUIRED:' + signature)
    return match.group()


def wrap(text, signature, owned_name, klass, params, result, owner_lines):
    """Keep the original body exactly; expose an ownership-serialized wrapper."""
    original = method(text, signature)
    original_head, body = original.split('\n', 1)
    method_name = signature.split('(', 1)[0]
    owned_signature = owned_name + signature[len(method_name):]
    owned_flags = 'private declared-synchronized' if ' declared-synchronized ' in original_head else 'private'
    owned = '.method ' + owned_flags + ' ' + owned_signature + '\n' + body
    if result == 'V':
        result_lines = ''
        return_lines = '    return-void'
        inactive_lines = '    return-void'
    else:
        suffix = '-object' if result.startswith('L') else ''
        result_lines = '    move-result' + suffix + ' v2\n'
        return_lines = '    return' + suffix + ' v2'
        inactive_lines = '    const/4 v2, 0x0\n' + return_lines
    # The original record keeps its Activity monitor inside the renamed body.
    # The new outer wrapper must acquire only the lease first (no inverse order).
    wrapper_head = original_head.replace(' declared-synchronized ', ' ')
    wrapper = wrapper_head + '\n    .locals 3\n\n' + owner_lines + f'''
    invoke-static {{v0}}, {M}->access$recoveryOwner({M}){L}
    move-result-object v1
    if-eqz v1, :recovery_inactive
    monitor-enter v1
    :recovery_try_start
    invoke-virtual {{v1, v0}}, {L}->owns(Ljava/lang/Object;)Z
    move-result v2
    if-eqz v2, :recovery_inactive_locked
    invoke-direct/range {{p0 .. p{params}}}, {klass}->{owned_signature}
{result_lines}    monitor-exit v1
{return_lines}
    :recovery_inactive_locked
    monitor-exit v1
    :recovery_try_end
    .catchall {{:recovery_try_start .. :recovery_try_end}} :recovery_catch
    :recovery_inactive
{inactive_lines}
    :recovery_catch
    move-exception v2
    monitor-exit v1
    throw v2
.end method
'''
    return replace_one(text, original, owned + '\n' + wrapper), original, owned


def main_hooks():
    restore_fields = []
    for name, field_type in [('evidence', 'Landroid/util/AtomicFile;'), ('events', 'Lorg/json/JSONArray;'),
                             ('createdElapsed', 'J'), ('editorActions', 'I'), ('connections', 'I'), ('droppedEvents', 'I')]:
        suffix = '-object' if field_type.startswith('L') else '-wide' if field_type == 'J' else ''
        restore_fields.extend([f'    iget{suffix} v1, v0, {S}->{name}:{field_type}',
                               f'    iput{suffix} v1, p0, {M}->{name}:{field_type}'])
    return f'''
# Recovery helpers: no durable claim/journal deletion or nonce substitution.
.method static access$recoveryOwner({M}){L}
    .locals 1
    iget-object v0, p0, {M}->sessionOwner:{L}
    return-object v0
.end method

.method private restoreRetainedSession()Z
    .locals 3
    invoke-virtual {{p0}}, {M}->getLastNonConfigurationInstance()Ljava/lang/Object;
    move-result-object v0
    instance-of v1, v0, {S}
    if-nez v1, :recovery_has_state
    const/4 v0, 0x0
    return v0
    :recovery_has_state
    check-cast v0, {S}
    iget-object v1, p0, {M}->runId:Ljava/lang/String;
    invoke-virtual {{v0, v1, p0}}, {S}->take(Ljava/lang/String;Ljava/lang/Object;){S}
    move-result-object v0
    iget-object v1, v0, {S}->lease:{L}
    iput-object v1, p0, {M}->sessionOwner:{L}
{chr(10).join(restore_fields)}
    iput-object v0, p0, {M}->restoreState:{S}
    const/4 v0, 0x1
    return v0
.end method

.method private restoreEditorText()V
    .locals 4
    iget-object v0, p0, {M}->restoreState:{S}
    if-eqz v0, :recovery_text_done
    iget-object v1, p0, {M}->editor:{E}
    iget-object v2, v0, {S}->text:Ljava/lang/String;
    invoke-virtual {{v1, v2}}, {E}->setText(Ljava/lang/CharSequence;)V
    iget v2, v0, {S}->selectionStart:I
    iget v3, v0, {S}->selectionEnd:I
    if-ltz v2, :recovery_no_selection
    invoke-virtual {{v1, v2, v3}}, {E}->setSelection(II)V
    goto :recovery_clear_restore_reference
    :recovery_no_selection
    invoke-virtual {{v1}}, {E}->getText()Landroid/text/Editable;
    move-result-object v2
    invoke-static {{v2}}, Landroid/text/Selection;->removeSelection(Landroid/text/Spannable;)V
    :recovery_clear_restore_reference
    const/4 v0, 0x0
    iput-object v0, p0, {M}->restoreState:{S}
    :recovery_text_done
    return-void
.end method

.method public onRetainNonConfigurationInstance()Ljava/lang/Object;
    .registers 16
    iget-object v1, p0, {M}->sessionOwner:{L}
    if-eqz v1, :recovery_retain_none_unlocked
    monitor-enter v1
    :recovery_retain_try_start
    invoke-virtual {{v1, p0}}, {L}->owns(Ljava/lang/Object;)Z
    move-result v0
    if-eqz v0, :recovery_retain_none
    iget-boolean v0, p0, {M}->failed:Z
    if-nez v0, :recovery_retain_none
    iget-object v14, p0, {M}->editor:{E}
    if-eqz v14, :recovery_retain_none
    new-instance v0, {S}
    move-object v2, p0
    iget-object v3, p0, {M}->runId:Ljava/lang/String;
    iget-object v4, p0, {M}->evidence:Landroid/util/AtomicFile;
    iget-object v5, p0, {M}->events:Lorg/json/JSONArray;
    iget-wide v6, p0, {M}->createdElapsed:J
    iget v8, p0, {M}->editorActions:I
    iget v9, p0, {M}->connections:I
    iget v10, p0, {M}->droppedEvents:I
    invoke-virtual {{v14}}, {E}->getText()Landroid/text/Editable;
    move-result-object v11
    invoke-virtual {{v11}}, Ljava/lang/Object;->toString()Ljava/lang/String;
    move-result-object v11
    invoke-virtual {{v14}}, {E}->getSelectionStart()I
    move-result v12
    invoke-virtual {{v14}}, {E}->getSelectionEnd()I
    move-result v13
    invoke-direct/range {{v0 .. v13}}, {S}-><init>({L}Ljava/lang/Object;Ljava/lang/String;Landroid/util/AtomicFile;Lorg/json/JSONArray;JIIILjava/lang/String;II)V
    monitor-exit v1
    return-object v0
    :recovery_retain_none
    const/4 v0, 0x0
    monitor-exit v1
    return-object v0
    :recovery_retain_try_end
    .catchall {{:recovery_retain_try_start .. :recovery_retain_try_end}} :recovery_retain_catch
    :recovery_retain_catch
    move-exception v0
    monitor-exit v1
    throw v0
    :recovery_retain_none_unlocked
    const/4 v0, 0x0
    return-object v0
.end method

.method protected onDestroy()V
    .locals 1
    iget-object v0, p0, {M}->sessionOwner:{L}
    if-eqz v0, :recovery_destroy_super
    invoke-virtual {{v0, p0}}, {L}->closeIfOwner(Ljava/lang/Object;)V
    const/4 v0, 0x0
    iput-object v0, p0, {M}->sessionOwner:{L}
    :recovery_destroy_super
    invoke-super {{p0}}, Landroid/app/Activity;->onDestroy()V
    return-void
.end method

.method protected onNewIntent(Landroid/content/Intent;)V
    .locals 0
    # Preserve the initial intent/session. A new Intent never takes writer ownership.
    invoke-super {{p0, p1}}, Landroid/app/Activity;->onNewIntent(Landroid/content/Intent;)V
    return-void
.end method
'''


def build(output):
    if output.exists():
        raise RuntimeError('NEW_OUTPUT_ONLY')
    output.mkdir(parents=True)
    before = {}
    for name, expected in PINS.items():
        raw = (SOURCE / REL / name).read_bytes()
        if sha(raw) != expected:
            raise RuntimeError('INSTALLED_SMALI_PREIMAGE_CHANGED:' + name)
        before[name] = raw.decode()
    changed = dict(before)
    text = changed['EditorContractActivity.smali']
    text = replace_one(text, '.field private final events:Lorg/json/JSONArray;', '.field private events:Lorg/json/JSONArray;')
    text = replace_one(text, '# direct methods', f'.field private sessionOwner:{L}\n\n.field private restoreState:{S}\n\n# direct methods')
    preserved = []
    for signature, name, count, ret in [
        ('record(Ljava/lang/String;Landroid/view/KeyEvent;ILorg/json/JSONObject;)V', 'recordOwned', 4, 'V'),
        ('lambda$onCreate$0$org-droidloom-qa-editorcontract-EditorContractActivity(Landroid/widget/TextView;ILandroid/view/KeyEvent;)Z',
         'editorActionOwned', 3, 'Z')]:
        text, original, renamed = wrap(text, signature, name, M, count, ret, '    move-object v0, p0\n')
        # The old synchronized record's body includes its original monitor; the
        # wrapper takes lease -> Activity, while retain takes only the lease.
        preserved.append({'source': 'EditorContractActivity.smali', 'method': signature,
                          'old_body_sha256': sha(original.split('\n', 1)[1].encode()),
                          'new_owned_body_sha256': sha(renamed.split('\n', 1)[1].encode())})
    text = replace_one(text, '    :try_start_23\n    new-instance v0, Ljava/io/File;',
        f'    :try_start_23\n    invoke-direct {{p0}}, {M}->restoreRetainedSession()Z\n'
        '    move-result v0\n    if-nez v0, :recovery_initialize_editor\n\n    new-instance v0, Ljava/io/File;')
    text = replace_one(text, '    .line 110\n    const-string v0, "created"',
        f'    new-instance v0, {L}\n    iget-object v2, p0, {M}->runId:Ljava/lang/String;\n'
        f'    invoke-direct {{v0, v2, p0}}, {L}-><init>(Ljava/lang/String;Ljava/lang/Object;)V\n'
        f'    iput-object v0, p0, {M}->sessionOwner:{L}\n\n    .line 110\n    const-string v0, "created"')
    text = replace_one(text, '    .line 116\n    new-instance v0, Landroid/widget/LinearLayout;',
        '    :recovery_initialize_editor\n    const/4 v1, -0x1\n\n    .line 116\n    new-instance v0, Landroid/widget/LinearLayout;')
    text = replace_one(text, '    .line 127\n    iget-object p1, p0, ' + M + '->editor:' + E,
        f'    invoke-direct {{p0}}, {M}->restoreEditorText()V\n\n'
        '    .line 127\n    iget-object p1, p0, ' + M + '->editor:' + E)
    text += main_hooks()
    changed['EditorContractActivity.smali'] = text
    for filename, klass, specifications, owner_lines in [
        ('EditorContractActivity$ContractEditText.smali', E,
         [('dispatchKeyEvent(Landroid/view/KeyEvent;)Z', 'dispatchKeyEventOwned', 1, 'Z'),
          ('onKeyPreIme(ILandroid/view/KeyEvent;)Z', 'onKeyPreImeOwned', 2, 'Z'),
          ('onCreateInputConnection(Landroid/view/inputmethod/EditorInfo;)Landroid/view/inputmethod/InputConnection;',
           'onCreateInputConnectionOwned', 1, 'Landroid/view/inputmethod/InputConnection;')],
         f'    iget-object v0, p0, {E}->this$0:{M}\n'),
        ('EditorContractActivity$ContractEditText$1.smali', W,
         [('performEditorAction(I)Z', 'performEditorActionOwned', 1, 'Z')],
         f'    iget-object v0, p0, {W}->this$1:{E}\n    iget-object v0, v0, {E}->this$0:{M}\n')]:
        text = changed[filename]
        for signature, name, count, ret in specifications:
            text, original, renamed = wrap(text, signature, name, klass, count, ret, owner_lines)
            preserved.append({'source': filename, 'method': signature,
                              'old_body_sha256': sha(original.split('\n', 1)[1].encode()),
                              'new_owned_body_sha256': sha(renamed.split('\n', 1)[1].encode())})
        changed[filename] = text
    assert all(x['old_body_sha256'] == x['new_owned_body_sha256'] for x in preserved)
    diff = ''
    records = {}
    for name, text in changed.items():
        path = output / REL / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        records[name] = {'preimage_sha256': sha(before[name].encode()), 'candidate_sha256': sha(text.encode()),
                         'bytes': len(text.encode()), 'byte_identical': before[name] == text}
        diff += ''.join(difflib.unified_diff(before[name].splitlines(True), text.splitlines(True),
                                            fromfile='installed-smali/' + name, tofile='candidate-smali/' + name))
    (output.parent / 'installed-lifecycle-recovery.patch').write_text(diff)
    report = {'schema': 'exact-installed-editor-lifecycle-source-patch-v1',
              'base_apk_sha256': '0d08f59024e4228e5d5b8f56742aafd1fbc04966d74224acd48542e09482743d',
              'base_dex_sha256': '07370b01a50f994d3ff465d1001989e48ff0d5c285564d35b97c81fdb9fa787d',
              'original_Java_recovered': False, 'original_signing_key_located': False,
              'manifest_resources_changed': False, 'Android_actions': 0, 'signed': False, 'installed': False,
              'original_methods_wrapped_with_verbatim_body': preserved, 'files': records,
              'declared_Java_types': ['SessionOwner', 'SessionOwner$Ticket', 'RetainedEditorState'],
              'compiler_synthetic_classes_included_by_actual_build': True,
              'candidate_needs_real_SDK_compile_and_DEX_assembly': True,
              'device_recreation_qualified': False, 'whole_app_production_ready': False}
    (output.parent / 'SOURCE_PATCH_REVIEW.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'state': 'EXACT_INSTALLED_SMALI_PATCH_PREPARED_HOST_ONLY',
                      'changed_original_classes': [n for n, r in records.items() if not r['byte_identical']],
                      'verbatim_owned_method_bodies': len(preserved), 'patch_sha256': sha(diff.encode())}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'candidate-smali')
    build(parser.parse_args().output)

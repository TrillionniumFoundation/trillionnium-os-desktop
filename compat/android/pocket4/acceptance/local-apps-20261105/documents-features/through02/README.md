# Documents additional features — actual evidence through Flow02

This append-only snapshot records three real SAF gates on the unchanged DocumentsUI APK: cancelling GET_CONTENT, cancelling OPEN_DOCUMENT_TREE, and granting persisted read/write access only to the uniquely owned fixture tree. It does not replace the previously reviewed Flow11 create/rename/open/persistence scope.

Flow01 stopped before installation or UI because the diagnostic parser did not accept the observed empty exit-info grammar. Flow02 completed the three gates and fixture setup, then failed on an incorrect namespace in the harness's New folder title selector. The saved dialog actually uses `com.android.documentsui:id/alertTitle`. No folder-name input or create confirmation was sent. The failed job and both original summaries remain unchanged.

Flow02 cleanup normally closed its two owned tasks, uninstalled the temporary helper, verified its CE/DE directories absent, and removed the exact fixture tree and staged APK. It used two exact host file unlinks. This proves cleanup; it gives no Files UI delete credit. The helper's two initial file writes are fixture setup, not Files UI creation.

The appended runtime review binds actual UID/PID/start time, namespaces, executable ELF and stable maps to the session. It also preserves a real collector limitation: de-duplication before candidate selection skipped 371 eligible code objects per observed process. These observations do not establish full executable coverage, engine exclusion, or long-duration resource stability. The unexecuted revision03 fixes the actual dialog selector and the selection order without extending the collection deadline.

`SCOPED_PROGRESS.json` contains a proposed new history entry, with evidence byte counts and hashes. Its `documents.provider` gate remains pending. Existing Flow11 passed gates stay unchanged. The complete feature session, search/sort, and whole-App qualification remain open.

This bundle contains selected actual evidence only. Full private command journals and raw runtime maps remain in the working evidence directory. Revision03 is prepared and reviewed but was not executed when this snapshot was produced; its later outcome must be appended separately.

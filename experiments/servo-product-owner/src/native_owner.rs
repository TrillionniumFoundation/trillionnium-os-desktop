//! Actual exact-pin Servo consumer. No mailbox, mock PageRuntime, listener,
//! action, navigation, extraction, policy grant or installed activation.
use std::cell::{Cell, RefCell};
use std::collections::VecDeque;
use std::rc::Rc;
use std::sync::Arc;
use std::thread::{self, ThreadId};
use std::time::{Duration, Instant};

use accesskit::{Node, NodeId, Role, Tree, TreeId, TreeUpdate};
use accesskit_consumer::{Tree as ConsumerTree, TreeChangeHandler};
use hepta_browser_actor::{
    JsonObject, JsonValue, PageOwnerSnapshot, ProfilePersistence, ServoCompletionDelivery,
    ServoEventLoopWaker, ServoRuntimeCompletion, ServoRuntimeEndpoint, ServoRuntimeError,
    ServoRuntimeOperation, ServoRuntimeOwner, closed_immutable_servo_runtime_pair,
};
use paint_api::rendering_context::RenderingContext;
use servo::{LoadStatus, NavigationRequest, Servo, WebView, WebViewBuilder, WebViewDelegate};
use url::Url;

pub const IMMUTABLE_PROFILE: &str = "immutable-read-only-v1";
pub const IMMUTABLE_DOCUMENT: &str = "data:text/html,<!DOCTYPE html><title>Immutable owner</title><main><h1>Owned semantic document</h1><p>Read only native Servo page</p></main>";
pub const OWNER_BUDGET: Duration = Duration::from_secs(5);
const MAX_UPDATES: usize = 64;
const MAX_NODES: usize = 256;
const MAX_TEXT_BYTES: usize = 4096;
const MAX_RESULT_BYTES: usize = 65536;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NativeOwnerError {
    WrongOwner,
    Retired,
    Invalidated,
    Bounds,
    Deadline,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NativeDrive {
    Idle,
    Pending,
    Completion(ServoCompletionDelivery),
    Retired,
}

#[derive(Default)]
struct Delegate {
    expected: RefCell<Option<servo::WebViewId>>,
    updates: RefCell<VecDeque<TreeUpdate>>,
    invalidated: Cell<bool>,
    document_established: Cell<bool>,
}
impl Delegate {
    fn current(&self, view: &WebView) -> bool {
        self.expected
            .borrow()
            .as_ref()
            .is_some_and(|id| *id == view.id())
    }
}
impl WebViewDelegate for Delegate {
    fn notify_accessibility_tree_update(&self, view: WebView, update: TreeUpdate) {
        if !self.current(&view)
            || update.nodes.len() > MAX_NODES
            || update.nodes.iter().any(|(_, node)| {
                node.label().is_some_and(|v| v.len() > MAX_TEXT_BYTES)
                    || node.value().is_some_and(|v| v.len() > MAX_TEXT_BYTES)
                    || node.url().is_some_and(|v| v.len() > MAX_TEXT_BYTES)
            })
        {
            self.invalidated.set(true);
            return;
        }
        let mut updates = self.updates.borrow_mut();
        if updates.len() >= MAX_UPDATES {
            self.invalidated.set(true);
        } else {
            updates.push_back(update);
        }
    }
    fn notify_load_status_changed(&self, view: WebView, status: LoadStatus) {
        if !self.current(&view) || self.document_established.get() && status != LoadStatus::Complete
        {
            self.invalidated.set(true);
        }
    }
    fn notify_crashed(&self, _view: WebView, _reason: String, _backtrace: Option<String>) {
        self.invalidated.set(true);
    }
    fn notify_closed(&self, _view: WebView) {
        self.invalidated.set(true);
    }
    fn notify_url_changed(&self, view: WebView, url: Url) {
        if !self.current(&view) || url != immutable_url() {
            self.invalidated.set(true);
        }
    }
    fn request_navigation(&self, _view: WebView, request: NavigationRequest) {
        request.deny();
    }
}
struct ChangeHandler;
impl TreeChangeHandler for ChangeHandler {
    fn node_added(&mut self, _: &accesskit_consumer::Node) {}
    fn node_updated(&mut self, _: &accesskit_consumer::Node, _: &accesskit_consumer::Node) {}
    fn focus_moved(
        &mut self,
        _: Option<&accesskit_consumer::Node>,
        _: Option<&accesskit_consumer::Node>,
    ) {
    }
    fn node_removed(&mut self, _: &accesskit_consumer::Node) {}
}
struct Pending {
    operation: ServoRuntimeOperation,
    completion: ServoRuntimeCompletion,
    deadline: Instant,
}
struct Binding {
    session_id: String,
    actor_webview_token: Option<String>,
    view_id: servo::WebViewId,
    view_tree_id: TreeId,
    document_tree_id: Option<TreeId>,
}

/// Owns the actual Servo instance, exactly one real native WebView and its
/// callback-derived semantic tree. Rc keeps this value !Send/!Sync. Every
/// authority entry checks creator PID and thread before touching RefCell state.
/// The caller supplies an actual Servo and context; no PageRuntime substitute
/// or caller-asserted semantic snapshot enters this adapter.
pub struct ClosedImmutableNativeOwner {
    creator_pid: u32,
    creator_thread: ThreadId,
    state: Option<NativeState>,
}
struct NativeState {
    servo: Servo,
    context: Rc<dyn RenderingContext>,
    bridge: ServoRuntimeOwner,
    view: Option<WebView>,
    delegate: Rc<Delegate>,
    tree: Option<ConsumerTree>,
    binding: Option<Binding>,
    pending: Option<Pending>,
    tree_revision: u64,
    retired: bool,
}
impl ClosedImmutableNativeOwner {
    pub fn new(
        servo: Servo,
        context: Rc<dyn RenderingContext>,
        waker: Arc<dyn ServoEventLoopWaker>,
    ) -> (ServoRuntimeEndpoint, Self) {
        let (endpoint, bridge) = closed_immutable_servo_runtime_pair(waker);
        (
            endpoint,
            Self {
                creator_pid: std::process::id(),
                creator_thread: thread::current().id(),
                state: Some(NativeState {
                    servo,
                    context,
                    bridge,
                    view: None,
                    delegate: Rc::new(Delegate::default()),
                    tree: None,
                    binding: None,
                    pending: None,
                    tree_revision: 0,
                    retired: false,
                }),
            },
        )
    }
    fn check_owner(&self) -> Result<(), NativeOwnerError> {
        if self.creator_pid != std::process::id() || self.creator_thread != thread::current().id() {
            Err(NativeOwnerError::WrongOwner)
        } else {
            Ok(())
        }
    }
    pub fn next_wake_deadline(&self) -> Result<Option<Instant>, NativeOwnerError> {
        self.check_owner()?;
        Ok(self
            .state
            .as_ref()
            .ok_or(NativeOwnerError::Retired)?
            .next_wake_deadline())
    }
    /// Drive only the creator's actual native owner. No inherited locks or
    /// Servo/RefCell state is touched before creator PID/thread verification.
    pub fn drive(&mut self) -> Result<NativeDrive, NativeOwnerError> {
        self.check_owner()?;
        self.state
            .as_mut()
            .ok_or(NativeOwnerError::Retired)?
            .drive()
    }
}
impl Drop for ClosedImmutableNativeOwner {
    fn drop(&mut self) {
        if self.creator_pid != std::process::id() || self.creator_thread != thread::current().id() {
            // Servo starts threads and is not a post-fork shutdown API. Do not
            // run inherited channel/engine destructors; child process retirement
            // owns its descriptor copies. This grants no forked execution.
            std::mem::forget(self.state.take());
        }
    }
}
impl NativeState {
    fn next_wake_deadline(&self) -> Option<Instant> {
        match (
            self.pending.as_ref().map(|p| p.deadline),
            self.bridge.next_wake_deadline(),
        ) {
            (Some(a), Some(b)) => Some(a.min(b)),
            (a, b) => a.or(b),
        }
    }
    /// One bounded source turn. Servo's native calls themselves are not
    /// preemptible by this module; checks bracket each call and completion.
    fn drive(&mut self) -> Result<NativeDrive, NativeOwnerError> {
        if self.retired {
            // Poll the already consumed completion exactly once; never start
            // another native command or recreate this retired owner.
            let _ = self.bridge.pump_one();
            return Ok(NativeDrive::Retired);
        }
        if let Some(pending) = &self.pending {
            if Instant::now() >= pending.deadline {
                return Ok(self.fail_pending(ServoRuntimeError::DeadlineExceeded));
            }
            if let Err(error) = pending.completion.ensure_current_peer() {
                return Ok(self.fail_pending(error));
            }
            if Instant::now() >= pending.deadline {
                return Ok(self.fail_pending(ServoRuntimeError::DeadlineExceeded));
            }
        }
        self.servo.spin_event_loop();
        if self.delegate.invalidated.get() {
            return Ok(self.fail_pending(ServoRuntimeError::BrowserCrashed));
        }
        if self.apply_updates().is_err() {
            return Ok(self.fail_pending(ServoRuntimeError::BrowserCrashed));
        }
        if matches!(
            self.bridge.pump_one(),
            hepta_browser_actor::ServoPumpResult::Retired
        ) {
            return Ok(self.fail_pending(ServoRuntimeError::BrowserCrashed));
        }
        if let Some(command) = self.bridge.take_command() {
            if self.pending.is_some() {
                return Ok(self.fail_pending(ServoRuntimeError::BrowserCrashed));
            }
            let (owner, operation, completion) = command.into_parts();
            let Some(local_stop) = Instant::now().checked_add(OWNER_BUDGET) else {
                return Ok(NativeDrive::Completion(
                    completion.complete_error(ServoRuntimeError::DeadlineExceeded),
                ));
            };
            let deadline = completion.deadline().min(local_stop);
            if let Err(error) = completion.ensure_current_peer() {
                return Ok(NativeDrive::Completion(completion.complete_error(error)));
            }
            if Instant::now() >= deadline {
                return Ok(NativeDrive::Completion(
                    completion.complete_error(ServoRuntimeError::DeadlineExceeded),
                ));
            }
            if self.admit(owner.as_ref(), &operation).is_err() {
                return Ok(NativeDrive::Completion(completion.complete_error(
                    ServoRuntimeError::PolicyDenied("native page identity/profile is not current"),
                )));
            }
            if let ServoRuntimeOperation::CreateSession { session_id, .. } = &operation {
                let view = WebViewBuilder::new(&self.servo, self.context.clone())
                    .delegate(self.delegate.clone())
                    .url(immutable_url())
                    .build();
                *self.delegate.expected.borrow_mut() = Some(view.id());
                let Some(view_tree_id) = view.set_accessibility_active(true) else {
                    self.retired = true;
                    return Ok(NativeDrive::Completion(
                        completion.complete_error(ServoRuntimeError::BrowserCrashed),
                    ));
                };
                self.binding = Some(Binding {
                    session_id: session_id.clone(),
                    actor_webview_token: None,
                    view_id: view.id(),
                    view_tree_id,
                    document_tree_id: None,
                });
                self.view = Some(view);
            }
            self.pending = Some(Pending {
                operation,
                completion,
                deadline,
            });
        }
        self.finish_ready()
    }
    fn admit(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        operation: &ServoRuntimeOperation,
    ) -> Result<(), NativeOwnerError> {
        match operation {
            ServoRuntimeOperation::Health => Ok(()),
            ServoRuntimeOperation::CreateSession { profile, .. }
                if self.binding.is_none()
                    && self.view.is_none()
                    && profile.persistence == ProfilePersistence::Ephemeral
                    && profile.profile_id == IMMUTABLE_PROFILE =>
            {
                Ok(())
            },
            ServoRuntimeOperation::Snapshot
            | ServoRuntimeOperation::Observe { .. }
            | ServoRuntimeOperation::Close => {
                let owner = owner.ok_or(NativeOwnerError::Invalidated)?;
                let binding = self.binding.as_mut().ok_or(NativeOwnerError::Invalidated)?;
                let view = self.view.as_ref().ok_or(NativeOwnerError::Invalidated)?;
                if owner.session_id != binding.session_id
                    || owner.session.revisions.document_generation != 1
                    || owner.current_url != immutable_url().as_str()
                    || view.id() != binding.view_id
                    || view.accesskit_tree_id() != Some(binding.view_tree_id)
                    || view.url() != Some(immutable_url())
                {
                    return Err(NativeOwnerError::Invalidated);
                }
                match &binding.actor_webview_token {
                    Some(token) if token != &owner.webview_token => {
                        Err(NativeOwnerError::Invalidated)
                    },
                    None => {
                        binding.actor_webview_token = Some(owner.webview_token.clone());
                        Ok(())
                    },
                    _ => Ok(()),
                }
            },
            _ => Err(NativeOwnerError::Invalidated),
        }
    }
    fn apply_updates(&mut self) -> Result<(), NativeOwnerError> {
        let updates = std::mem::take(&mut *self.delegate.updates.borrow_mut());
        for update in updates {
            let binding = self.binding.as_mut().ok_or(NativeOwnerError::Invalidated)?;
            let is_document = update
                .nodes
                .iter()
                .any(|(_, node)| node.role() == Role::RootWebArea);
            if is_document {
                if binding
                    .document_tree_id
                    .is_some_and(|id| id != update.tree_id)
                {
                    return Err(NativeOwnerError::Invalidated);
                }
                binding.document_tree_id = Some(update.tree_id);
            }
            if update.tree_id != binding.view_tree_id
                && Some(update.tree_id) != binding.document_tree_id
            {
                return Err(NativeOwnerError::Invalidated);
            }

            if self.tree.is_none() {
                let binding = self.binding.as_ref().ok_or(NativeOwnerError::Invalidated)?;
                let root_id = NodeId(0);
                let graft_id = NodeId(1);
                let mut root = Node::new(Role::GenericContainer);
                root.set_children(vec![graft_id]);
                let mut graft = Node::new(Role::GenericContainer);
                graft.set_tree_id(binding.view_tree_id);
                self.tree = Some(ConsumerTree::new(
                    TreeUpdate {
                        nodes: vec![(root_id, root), (graft_id, graft)],
                        tree: Some(Tree {
                            root: root_id,
                            toolkit_name: None,
                            toolkit_version: None,
                        }),
                        tree_id: TreeId::ROOT,
                        focus: root_id,
                    },
                    true,
                ));
            }
            self.tree
                .as_mut()
                .expect("tree initialized")
                .update_and_process_changes(update, &mut ChangeHandler);
            self.tree_revision = self
                .tree_revision
                .checked_add(1)
                .ok_or(NativeOwnerError::Bounds)?;
            // A WebView root arrives before its document graft. Missing
            // document means pending, never successful snapshot; bounds fail closed.
            if matches!(self.snapshot(), Err(NativeOwnerError::Bounds)) {
                return Err(NativeOwnerError::Bounds);
            }
        }
        Ok(())
    }
    fn snapshot(&self) -> Result<JsonObject, NativeOwnerError> {
        let tree = self.tree.as_ref().ok_or(NativeOwnerError::Invalidated)?;
        let view = self.view.as_ref().ok_or(NativeOwnerError::Invalidated)?;
        let mut queue = VecDeque::from([tree.state().root()]);
        let mut nodes = Vec::new();
        let mut document = None;
        let mut count = 0;
        while let Some(node) = queue.pop_front() {
            count += 1;
            if count > MAX_NODES || queue.len() + node.children().len() > MAX_NODES {
                return Err(NativeOwnerError::Bounds);
            }
            queue.extend(node.children());
            let (local_id, tree_id) = node.locate();
            if tree_id == TreeId::ROOT || node.is_graft() {
                continue;
            }
            if node.role() == Role::RootWebArea {
                if document.replace(tree_id).is_some() {
                    return Err(NativeOwnerError::Invalidated);
                }
            }
            let text = node.value();
            let name = node.label();
            let href = node.url();
            if text.as_ref().is_some_and(|v| v.len() > MAX_TEXT_BYTES)
                || name.as_ref().is_some_and(|v| v.len() > MAX_TEXT_BYTES)
                || href.is_some_and(|v| v.len() > MAX_TEXT_BYTES)
            {
                return Err(NativeOwnerError::Bounds);
            }
            let bounds = match node.raw_bounds() {
                Some(b) if [b.x0, b.y0, b.x1, b.y1].iter().all(|v| v.is_finite()) => {
                    JsonValue::Array(
                        [b.x0, b.y0, b.x1, b.y1]
                            .iter()
                            .map(|v| JsonValue::String(v.to_string()))
                            .collect(),
                    )
                },
                Some(_) => return Err(NativeOwnerError::Bounds),
                None => JsonValue::Null,
            };
            nodes.push(JsonValue::Object(object([
                ("node_id", JsonValue::String(format!("{}", local_id.0))),
                ("tree_id", JsonValue::String(tree_id.0.to_string())),
                ("role", JsonValue::String(format!("{:?}", node.role()))),
                ("name", optional(name.as_deref())),
                ("text", optional(text.as_deref())),
                ("href", optional(href)),
                ("raw_bounds_css_decimal", bounds),
            ])));
        }
        let document = document.ok_or(NativeOwnerError::Invalidated)?;
        if self.binding.as_ref().and_then(|v| v.document_tree_id) != Some(document) {
            return Err(NativeOwnerError::Invalidated);
        }
        let result = object([
            (
                "runtime",
                JsonValue::String("actual-servo-immutable-owner".into()),
            ),
            (
                "native_webview_id",
                JsonValue::String(format!("{:?}", view.id())),
            ),
            (
                "document_tree_id",
                JsonValue::String(document.0.to_string()),
            ),
            (
                "native_tree_revision",
                JsonValue::Integer(
                    i64::try_from(self.tree_revision).map_err(|_| NativeOwnerError::Bounds)?,
                ),
            ),
            ("nodes", JsonValue::Array(nodes)),
        ]);
        if JsonValue::Object(result.clone())
            .canonical_bytes()
            .map_err(|_| NativeOwnerError::Bounds)?
            .len()
            > MAX_RESULT_BYTES
        {
            return Err(NativeOwnerError::Bounds);
        }
        Ok(result)
    }
    fn finish_ready(&mut self) -> Result<NativeDrive, NativeOwnerError> {
        let Some(pending) = self.pending.as_ref() else {
            return Ok(NativeDrive::Idle);
        };
        if Instant::now() >= pending.deadline {
            return Ok(self.fail_pending(ServoRuntimeError::DeadlineExceeded));
        }
        if let Err(error) = pending.completion.ensure_current_peer() {
            return Ok(self.fail_pending(error));
        }
        if Instant::now() >= pending.deadline {
            return Ok(self.fail_pending(ServoRuntimeError::DeadlineExceeded));
        }
        let ready = matches!(
            pending.operation,
            ServoRuntimeOperation::Health | ServoRuntimeOperation::Close
        ) || self
            .view
            .as_ref()
            .is_some_and(|v| v.load_status() == LoadStatus::Complete)
            && self.snapshot().is_ok();
        if !ready {
            return Ok(NativeDrive::Pending);
        }
        let pending = self.pending.take().expect("pending present");
        if matches!(pending.operation, ServoRuntimeOperation::Close) {
            // No public PIN API confirms pipeline retirement after handle drop.
            // Therefore release is a possible effect with an unknown outcome.
            self.retire_native();
            return Ok(NativeDrive::Completion(
                pending
                    .completion
                    .complete_error(ServoRuntimeError::BrowserCrashed),
            ));
        }
        let result = if matches!(pending.operation, ServoRuntimeOperation::Health) {
            object([
                (
                    "runtime",
                    JsonValue::String("actual-servo-immutable-owner".into()),
                ),
                ("external_effect_authority", JsonValue::Bool(false)),
            ])
        } else {
            let result = match self.snapshot() {
                Ok(result) => result,
                Err(_) => {
                    self.retire_native();
                    return Ok(NativeDrive::Completion(
                        pending
                            .completion
                            .complete_error(ServoRuntimeError::BrowserCrashed),
                    ));
                },
            };
            self.delegate.document_established.set(true);
            result
        };
        // Capture is synchronous on the native owner; no Servo call/callback
        // may run between this final custody check and consuming completion.
        if Instant::now() >= pending.deadline {
            self.retire_native();
            return Ok(NativeDrive::Completion(
                pending
                    .completion
                    .complete_error(ServoRuntimeError::DeadlineExceeded),
            ));
        }
        if let Err(error) = pending.completion.ensure_current_peer() {
            self.retire_native();
            return Ok(NativeDrive::Completion(
                pending.completion.complete_error(error),
            ));
        }
        if Instant::now() >= pending.deadline {
            self.retire_native();
            return Ok(NativeDrive::Completion(
                pending
                    .completion
                    .complete_error(ServoRuntimeError::DeadlineExceeded),
            ));
        }
        let delivery = pending.completion.complete_success(
            result,
            self.view
                .as_ref()
                .and_then(|v| v.url())
                .map(|url| url.to_string()),
        );
        if Instant::now() >= pending.deadline {
            // Completion is only queued to the native bridge at this point;
            // retire that bridge before any later pump forwards a late value.
            self.retire_native();
            self.bridge.retire();
            return Ok(NativeDrive::Retired);
        }
        Ok(NativeDrive::Completion(delivery))
    }
    fn fail_pending(&mut self, error: ServoRuntimeError) -> NativeDrive {
        self.retire_native();
        match self.pending.take() {
            Some(p) => NativeDrive::Completion(p.completion.complete_error(error)),
            None => {
                self.bridge.retire();
                NativeDrive::Retired
            },
        }
    }
    fn retire_native(&mut self) {
        // Reserve retirement before releasing any possible engine effect.
        // No remaining semantic tree, callback or native handle is a reusable
        // owner after a late/cancelled/revoked completion.
        self.retired = true;
        self.binding.take();
        self.tree.take();
        self.delegate.document_established.set(false);
        self.delegate.invalidated.set(true);
        self.delegate.expected.borrow_mut().take();
        self.delegate.updates.borrow_mut().clear();
        self.view.take();
    }
}
fn optional(value: Option<&str>) -> JsonValue {
    value.map_or(JsonValue::Null, |v| JsonValue::String(v.into()))
}
fn object<const N: usize>(entries: [(&str, JsonValue); N]) -> JsonObject {
    entries
        .into_iter()
        .map(|(key, value)| (key.into(), value))
        .collect()
}

fn immutable_url() -> Url {
    Url::parse(IMMUTABLE_DOCUMENT).expect("constant immutable URL")
}

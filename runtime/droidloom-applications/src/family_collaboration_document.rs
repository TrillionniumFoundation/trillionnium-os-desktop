//! Actual, reversible search of one normally declared readonly Feishu document.
//! No arbitrary URI/intent, external message, document edit, upload or share is
//! exposed. A comparison fixture never substitutes for the held UI histories.
use super::*;

const SEARCH_ENTRY_IDS: &[&str] = &[
    "common_searchbar",
    "search_icon",
    "searchIcon",
    "search_mag_icon",
    "search_bar",
    "search_bar_fake",
];
const INPUT_IDS: &[&str] = &[
    "common_searchbar_edit",
    "edit_query",
    "searchEditText",
    "search_edit_et",
    "search_edit_text",
    "search_et",
    "search_input",
    "search_src_text",
];
const DOCUMENT_TITLE_IDS: &[&str] = &["doc_title", "small_doc_title", "thumbnail_doc_title"];

fn matches_identity(fixture: &FeishuReadonlyFixture, workspace: &WorkspaceIdentity) -> bool {
    same_title(&fixture.workspace_name, &workspace.tenant)
        && same_title(&fixture.account_name, &workspace.account)
}
fn top_control(trace: &Trace, origin: usize, node: &Value) -> Result<Option<Rect>, String> {
    let ns = nodes(trace.body(origin)?)?;
    let window = Rect::parse(&trace.body(origin)?["window_context"]["selected_window"]["bounds"])?;
    let selected = Rect::parse(&node["bounds_array"])?;
    let mut possible = ns
        .iter()
        .filter(|n| usable(n) && n["clickable"] == true && n["editable"] == false)
        .filter_map(|n| Rect::parse(&n["bounds_array"]).ok())
        .filter(|r| {
            r.contains(selected)
                && window.contains(*r)
                && r.0[3] <= window.0[1] + 2 * window.height() / 5
                && r.height() <= window.height() / 4
        })
        .collect::<Vec<_>>();
    possible.sort_by_key(|r| r.area());
    possible.dedup();
    Ok(possible.first().copied())
}
fn search_entry(trace: &Trace, frame: usize) -> Result<Option<Target>, String> {
    let f = &trace.frames[frame];
    let candidates = nodes(trace.body(f.after)?)?
        .iter()
        .filter(|n| {
            usable(n)
                && n["editable"] == false
                && SEARCH_ENTRY_IDS.iter().any(|id| resource(n, id))
                && trace.rendered(frame, n)
        })
        .collect::<Vec<_>>();
    if candidates.len() != 1 {
        return Ok(None);
    }
    let node = candidates[0];
    let Some(container) = top_control(trace, f.after, node)? else {
        return Ok(None);
    };
    choose(trace, f.after, Role::SearchEntry, node, Some(container))
}
fn input(trace: &Trace, origin: usize, expected: &str) -> Result<Target, String> {
    let candidates = nodes(trace.body(origin)?)?
        .iter()
        .filter(|n| {
            usable(n)
                && n["editable"] == true
                && n["password"] == false
                && text(n, "text") == expected
                && INPUT_IDS.iter().any(|id| resource(n, id))
        })
        .collect::<Vec<_>>();
    need(
        candidates.len() == 1,
        "declared collaboration query requires one exact actual search input",
    )?;
    choose(trace, origin, Role::Input, candidates[0], None)?
        .ok_or("collaboration query input has no unique normal selector".into())
}
fn submit(trace: &Trace, origin: usize) -> Result<Target, String> {
    let candidates = nodes(trace.body(origin)?)?
        .iter()
        .filter(|n| {
            usable(n)
                && n["editable"] == false
                && ["搜索", "搜尋", "search"].contains(&norm(text(n, "text")).as_str())
        })
        .collect::<Vec<_>>();
    need(
        candidates.len() == 1,
        "one actual collaboration search submission control required",
    )?;
    let node = candidates[0];
    let container = top_control(trace, origin, node)?
        .ok_or("collaboration search control is outside the observed top search surface")?;
    choose(trace, origin, Role::Submit, node, Some(container))?
        .ok_or("collaboration submit control is ambiguous".into())
}
fn back(trace: &Trace, origin: usize) -> Result<Target, String> {
    let candidates = nodes(trace.body(origin)?)?
        .iter()
        .filter(|n| usable(n) && n["editable"] == false && resource(n, "iv_back"))
        .collect::<Vec<_>>();
    need(
        candidates.len() == 1,
        "one actual original collaboration back control required",
    )?;
    let node = candidates[0];
    let container = top_control(trace, origin, node)?
        .ok_or("collaboration back control leaves its observed header")?;
    choose(trace, origin, Role::Back, node, Some(container))?
        .ok_or("collaboration back control is ambiguous".into())
}
fn result(trace: &Trace, frame: usize, fixture: &FeishuReadonlyFixture) -> Result<Target, String> {
    let f = &trace.frames[frame];
    let ns = nodes(trace.body(f.after)?)?;
    input(trace, f.after, &fixture.unicode_query)?;
    let titles = ns
        .iter()
        .filter(|n| {
            usable(n)
                && n["editable"] == false
                && DOCUMENT_TITLE_IDS.iter().any(|id| resource(n, id))
                && same_title(text(n, "text"), &fixture.document_title)
                && trace.rendered(frame, n)
        })
        .collect::<Vec<_>>();
    need(
        titles.len() == 1,
        "one actual original document result must match the declared title",
    )?;
    let title = titles[0];
    let title_rect = Rect::parse(&title["bounds_array"])?;
    let hints = ns
        .iter()
        .filter(|n| {
            usable(n)
                && n["editable"] == false
                && same_title(text(n, "text"), &fixture.document_result_hint)
                && trace.rendered(frame, n)
        })
        .filter_map(|n| Rect::parse(&n["bounds_array"]).ok())
        .collect::<Vec<_>>();
    need(
        hints.len() == 1,
        "declared readonly document result metadata is absent or ambiguous",
    )?;
    let mut cards = ns
        .iter()
        .filter(|n| usable(n) && n["editable"] == false && n["clickable"] == true)
        .filter_map(|n| Rect::parse(&n["bounds_array"]).ok())
        .filter(|r| {
            r.contains(title_rect)
                && r.contains(hints[0])
                && f.window.contains(*r)
                && r.height() < f.window.height() / 2
        })
        .collect::<Vec<_>>();
    cards.sort_by_key(|r| r.area());
    cards.dedup();
    let card = cards
        .first()
        .copied()
        .ok_or("declared document title and metadata do not share one bounded result card")?;
    choose(trace, f.after, Role::Document, title, Some(card))?
        .ok_or("declared document result has no unique normal selector".into())
}
fn image_matches(actual: &Patch, expected: &[u8; 768]) -> bool {
    actual.rgb.len() == 768
        && actual
            .rgb
            .iter()
            .zip(expected)
            .map(|(a, b)| u64::from(a.abs_diff(*b)))
            .sum::<u64>()
            <= 768 * 12
        && actual
            .rgb
            .iter()
            .zip(expected)
            .filter(|(a, b)| a.abs_diff(**b) > 24)
            .count()
            <= 38
}
#[derive(Clone, Debug, Eq, PartialEq)]
struct DocumentView {
    region: Rect,
    body_sha256: String,
    image_sha256: Option<String>,
    pixels_sha256: String,
}
fn document(
    trace: &Trace,
    frame: usize,
    fixture: &FeishuReadonlyFixture,
    scrolled: bool,
) -> Result<DocumentView, String> {
    let f = &trace.frames[frame];
    let ns = nodes(trace.body(f.after)?)?;
    need(
        !authentication_surface(trace.body(f.after)?)?,
        "readonly document returned to authentication",
    )?;
    let title = ns
        .iter()
        .filter(|n| {
            usable(n)
                && n["editable"] == false
                && same_title(text(n, "text"), &fixture.document_title)
                && trace.rendered(frame, n)
        })
        .count();
    need(
        title == 1,
        "actual readonly document title differs from its declared result",
    )?;
    let wanted = if scrolled {
        &fixture.scrolled_body_markers
    } else {
        &fixture.before_body_markers
    };
    let mut actual = Vec::new();
    let mut rectangles = Vec::new();
    for marker in wanted {
        let found = ns
            .iter()
            .filter(|n| {
                usable(n)
                    && n["editable"] == false
                    && text(n, "text").contains(marker.as_str())
                    && trace.rendered(frame, n)
            })
            .collect::<Vec<_>>();
        need(
            found.len() == 1,
            "actual rendered document body does not contain each distinct declared marker",
        )?;
        actual.push(text(found[0], "text").to_owned());
        rectangles.push(Rect::parse(&found[0]["bounds_array"])?);
    }
    let expected = fixture.image_rgb().map_err(|e| e.to_string())?;
    let matched_images = ns
        .iter()
        .filter(|n| image(n) && trace.rendered(frame, n))
        .filter_map(|n| Rect::parse(&n["bounds_array"]).ok())
        .filter(|r| {
            f.patches
                .get(r)
                .is_some_and(|p| image_matches(p, &expected))
        })
        .collect::<std::collections::BTreeSet<_>>();
    let image_rect = if scrolled {
        None
    } else {
        need(
            matched_images.len() == 1,
            "actual decoded document image differs from the declared comparison image",
        )?;
        matched_images.iter().next().copied()
    };
    let regions = ns
        .iter()
        .filter(|n| usable(n) && n["scrollable"] == true && n["editable"] == false)
        .filter_map(|n| Rect::parse(&n["bounds_array"]).ok())
        .filter(|r| {
            f.window.contains(*r)
                && r.height() >= f.window.height() / 3
                && rectangles.iter().all(|part| r.contains(*part))
                && image_rect.is_none_or(|image| r.contains(image))
                && f.patches.contains_key(r)
        })
        .collect::<std::collections::BTreeSet<_>>();
    let region =
        regions.iter().min_by_key(|r| r.area()).copied().ok_or(
            "declared readonly body and image lack one actually rendered scroll container",
        )?;
    Ok(DocumentView {
        region,
        body_sha256: digest(&serde_json::to_vec(&actual).map_err(|e| e.to_string())?),
        image_sha256: image_rect.map(|r| f.patches[&r].sha256.clone()),
        pixels_sha256: f.patches[&region].sha256.clone(),
    })
}
fn scroll(trace: &Trace, frame: usize, view: &DocumentView) -> Result<Target, String> {
    let f = &trace.frames[frame];
    let choices = nodes(trace.body(f.after)?)?
        .iter()
        .filter(|n| {
            usable(n)
                && n["scrollable"] == true
                && n["editable"] == false
                && Rect::parse(&n["bounds_array"]).ok() == Some(view.region)
        })
        .collect::<Vec<_>>();
    need(
        choices.len() == 1,
        "readonly document scroll container is ambiguous",
    )?;
    choose(trace, f.after, Role::Scroll, choices[0], Some(view.region))?
        .ok_or("readonly document scroll container lacks a unique normal selector".into())
}
fn action(
    trace: &Trace,
    index: usize,
    target: Target,
    op: Operation,
    written: Option<&str>,
) -> Result<(), String> {
    let step = trace
        .steps
        .get(index)
        .ok_or("declared document retained action absent")?;
    need(
        step.op == op
            && step.written.as_deref() == written
            && step
                .target
                .as_ref()
                .is_some_and(|(origin, role, node, container)| {
                    *origin == target.origin
                        && *role == target.role
                        && *node == target.node
                        && *container == target.container
                })
            && target.origin < index,
        "declared document action detached from its observed target",
    )
}

pub(super) struct DocumentExecution {
    fixture: FeishuReadonlyFixture,
    origin: usize,
    search: usize,
    input_frame: usize,
    typed: usize,
    typed_dump: usize,
    submit: usize,
    results: usize,
    opened: usize,
    before_frame: usize,
    before_view: DocumentView,
    forward: usize,
    lower_frame: usize,
    lower_view: DocumentView,
    backward: usize,
    restored_frame: usize,
    restored_view: DocumentView,
    returned: usize,
    returned_frame: usize,
    cleared: usize,
    clear_dump: usize,
    back: usize,
    home: usize,
}
impl DocumentExecution {
    pub(super) fn actions(&self) -> u32 {
        9
    }
    pub(super) fn origin(&self) -> usize {
        self.origin
    }
    pub(super) fn guard(
        &self,
        trace: &Trace,
        workspace_identity: &WorkspaceIdentity,
    ) -> Result<(), String> {
        self.fixture.validate().map_err(|e| e.to_string())?;
        need(
            matches_identity(&self.fixture, workspace_identity),
            "declared readonly fixture belongs to another observed workspace/account",
        )?;
        let f = |n: usize| trace.frames.get(n).ok_or("declared document frame absent");
        let entry = search_entry(trace, self.origin)?
            .ok_or("declared document source search entry absent")?;
        action(trace, self.search, entry, Operation::Click, None)?;
        let origin = f(self.origin)?.after;
        need(
            origin < self.search && self.search < f(self.input_frame)?.before,
            "search entry lost its real original frame ordering",
        )?;
        action(
            trace,
            self.typed,
            input(trace, f(self.input_frame)?.after, "")?,
            Operation::SetText,
            Some(&self.fixture.unicode_query),
        )?;
        need(
            trace.steps[self.typed_dump].op == Operation::Dump && self.typed < self.typed_dump,
            "typed Unicode lacks its independent subsequent real dump",
        )?;
        input(trace, self.typed_dump, &self.fixture.unicode_query)?;
        action(
            trace,
            self.submit,
            submit(trace, self.typed_dump)?,
            Operation::Click,
            None,
        )?;
        need(
            self.submit < f(self.results)?.before,
            "search results precede actual submission",
        )?;
        action(
            trace,
            self.opened,
            result(trace, self.results, &self.fixture)?,
            Operation::Click,
            None,
        )?;
        need(
            self.opened < f(self.before_frame)?.before,
            "document body precedes its actual open",
        )?;
        need(
            document(trace, self.before_frame, &self.fixture, false)? == self.before_view,
            "retained original document body/image changed",
        )?;
        action(
            trace,
            self.forward,
            scroll(trace, self.before_frame, &self.before_view)?,
            Operation::Forward,
            None,
        )?;
        need(
            self.forward < f(self.lower_frame)?.before,
            "scrolled body precedes actual scroll",
        )?;
        need(
            document(trace, self.lower_frame, &self.fixture, true)? == self.lower_view,
            "retained scrolled document body changed",
        )?;
        action(
            trace,
            self.backward,
            scroll(trace, self.lower_frame, &self.lower_view)?,
            Operation::Backward,
            None,
        )?;
        need(
            self.backward < f(self.restored_frame)?.before,
            "restored body precedes actual reverse scroll",
        )?;
        need(
            document(trace, self.restored_frame, &self.fixture, false)? == self.restored_view
                && self.before_view.region == self.lower_view.region
                && self.before_view.region == self.restored_view.region
                && self.before_view.body_sha256 == self.restored_view.body_sha256
                && self.before_view.image_sha256 == self.restored_view.image_sha256
                && self.before_view.body_sha256 != self.lower_view.body_sha256
                && materially_changed(
                    &f(self.before_frame)?.patches[&self.before_view.region],
                    &f(self.lower_frame)?.patches[&self.lower_view.region],
                ),
            "readonly document has no actual changed lower body and restored original body/image",
        )?;
        action(
            trace,
            self.returned,
            back(trace, f(self.restored_frame)?.after)?,
            Operation::Click,
            None,
        )?;
        need(
            self.returned < f(self.returned_frame)?.before,
            "query return precedes actual back",
        )?;
        result(trace, self.returned_frame, &self.fixture)?;
        action(
            trace,
            self.cleared,
            input(
                trace,
                f(self.returned_frame)?.after,
                &self.fixture.unicode_query,
            )?,
            Operation::SetText,
            Some(""),
        )?;
        need(
            trace.steps[self.clear_dump].op == Operation::Dump && self.cleared < self.clear_dump,
            "query restoration lacks independent actual dump",
        )?;
        input(trace, self.clear_dump, "")?;
        action(
            trace,
            self.back,
            back(trace, self.clear_dump)?,
            Operation::Click,
            None,
        )?;
        need(
            self.back < f(self.home)?.before
                && workspace(trace, self.home)?.as_ref() == Some(workspace_identity)
                && page_content(trace, self.home, Page::Messages)?.map(|v| v.body_sha256)
                    == page_content(trace, self.origin, Page::Messages)?.map(|v| v.body_sha256),
            "readonly document roundtrip did not restore the actual original Messages body/workspace",
        )?;
        need(
            self.home + 1 == trace.frames.len(),
            "declared document has extra unowned image frames",
        )?;
        Ok(())
    }
    pub(super) fn comparison(&self) -> Value {
        json!({"normal_declared_fixture_sha256":digest(&serde_json::to_vec(&self.fixture).unwrap()),
            "unicode_query_sha256":digest(self.fixture.unicode_query.as_bytes()),
            "document_title_sha256":digest(self.fixture.document_title.as_bytes()),
            "original_body_sha256":self.before_view.body_sha256,
            "scrolled_body_sha256":self.lower_view.body_sha256,
            "restored_body_sha256":self.restored_view.body_sha256,
            "actual_image_sha256":self.before_view.image_sha256,
            "query_input_original_empty":true,"only_owned_query_restored_empty":true,
            "declared_image_is_comparison_not_observation":true,
            "document_edit_upload_share_or_external_message_attempted":false})
    }
}

pub(super) fn run(
    trace: &mut Trace,
    s: &mut NativeUiSession<'_, '_>,
    i: &NativeApplicationInspector,
    fixture: &FeishuReadonlyFixture,
    workspace_identity: &WorkspaceIdentity,
    origin: usize,
    end: Instant,
) -> Result<Option<DocumentExecution>, String> {
    fixture.validate().map_err(|e| e.to_string())?;
    if !matches_identity(fixture, workspace_identity) {
        return Ok(None);
    }
    let Some(entry) = search_entry(trace, origin)? else {
        return Ok(None);
    };
    let search = trace.perform(s, i, entry, Operation::Click, None, end)?;
    let input_frame = trace.frame(s, i, end)?;
    let target = input(trace, trace.frames[input_frame].after, "")?;
    let typed = trace.perform(
        s,
        i,
        target,
        Operation::SetText,
        Some(&fixture.unicode_query),
        end,
    )?;
    let typed_dump = trace.dump(s, i, end)?;
    input(trace, typed_dump, &fixture.unicode_query)?;
    let target = submit(trace, typed_dump)?;
    let submitted = trace.perform(s, i, target, Operation::Click, None, end)?;
    let results = trace.frame(s, i, end)?;
    let target = result(trace, results, fixture)?;
    let opened = trace.perform(s, i, target, Operation::Click, None, end)?;
    let before_frame = trace.frame(s, i, end)?;
    let before_view = document(trace, before_frame, fixture, false)?;
    let target = scroll(trace, before_frame, &before_view)?;
    let forward = trace.perform(s, i, target, Operation::Forward, None, end)?;
    let lower_frame = trace.frame(s, i, end)?;
    let lower_view = document(trace, lower_frame, fixture, true)?;
    let target = scroll(trace, lower_frame, &lower_view)?;
    let backward = trace.perform(s, i, target, Operation::Backward, None, end)?;
    let restored_frame = trace.frame(s, i, end)?;
    let restored_view = document(trace, restored_frame, fixture, false)?;
    let target = back(trace, trace.frames[restored_frame].after)?;
    let returned = trace.perform(s, i, target, Operation::Click, None, end)?;
    let returned_frame = trace.frame(s, i, end)?;
    result(trace, returned_frame, fixture)?;
    let target = input(
        trace,
        trace.frames[returned_frame].after,
        &fixture.unicode_query,
    )?;
    let cleared = trace.perform(s, i, target, Operation::SetText, Some(""), end)?;
    let clear_dump = trace.dump(s, i, end)?;
    input(trace, clear_dump, "")?;
    let target = back(trace, clear_dump)?;
    let back = trace.perform(s, i, target, Operation::Click, None, end)?;
    let home = trace.frame(s, i, end)?;
    let value = DocumentExecution {
        fixture: fixture.clone(),
        origin,
        search,
        input_frame,
        typed,
        typed_dump,
        submit: submitted,
        results,
        opened,
        before_frame,
        before_view,
        forward,
        lower_frame,
        lower_view,
        backward,
        restored_frame,
        restored_view,
        returned,
        returned_frame,
        cleared,
        clear_dump,
        back,
        home,
    };
    value.guard(trace, workspace_identity)?;
    before(end)?;
    Ok(Some(value))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn readonly_vocabulary_never_types_into_page_result_back_or_scroll() {
        for role in [
            Role::Page,
            Role::SearchEntry,
            Role::Input,
            Role::Submit,
            Role::Document,
            Role::Back,
            Role::Scroll,
        ] {
            for op in [
                Operation::Dump,
                Operation::Click,
                Operation::SetText,
                Operation::Forward,
                Operation::Backward,
            ] {
                assert!(!allowed_operation(role, op, Some("message\n")));
                if role != Role::Input {
                    assert!(!allowed_operation(role, op, Some("只读 query")));
                }
            }
        }
        assert!(allowed_operation(
            Role::Input,
            Operation::SetText,
            Some("只读 query")
        ));
        assert!(allowed_operation(Role::Input, Operation::SetText, Some("")));
        assert!(!allowed_operation(Role::Input, Operation::Click, None));
    }
    #[test]
    fn declared_image_comparison_requires_actual_nontrivial_pixel_match() {
        let expected = std::array::from_fn::<u8, 768, _>(|n| (n % 251) as u8);
        let value = Patch {
            rgb: expected.to_vec(),
            sha256: digest(&expected),
        };
        assert!(image_matches(&value, &expected));
        let mut changed = value.clone();
        for n in 0..39 {
            changed.rgb[n] = changed.rgb[n].wrapping_add(50);
        }
        assert!(!image_matches(&changed, &expected));
        let mut blank = value.clone();
        blank.rgb.fill(255);
        assert!(!image_matches(&blank, &expected));
        let mut short = value.clone();
        short.rgb.pop();
        assert!(!image_matches(&short, &expected));
    }
}

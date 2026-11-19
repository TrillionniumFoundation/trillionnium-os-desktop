//! Finite browser command and input-role specifications.
//!
//! This crate cannot execute a process, open a runtime, deserialize an authority,
//! or grant production readiness. Its values are plans and manifest checks only.
//! The future native adapter must borrow the actual ReadyTreeWitness, retain the
//! actual framework and package identity, select sealed action inputs, and prove
//! the real exec/retirement. The existing read-worker FD protocol is unchanged.

pub const SCOPE: &str = "fixed_browser_action_v1";
pub const PACKAGE: &str = "org.mozilla.firefox";
pub const SOURCE_EXECUTABLE: &str = "/system/bin/cmd";
pub const PRIVATE_EXECUTABLE: &str = "/.droidloom-browser/cmd";
pub const PROCESS_CONTEXT: &str = "u:r:droidloom_browser_action:s0";
pub const EXECUTABLE_CONTEXT: &str = "u:object_r:droidloom_browser_action_exec:s0";
const MAX_EXECUTABLE_BYTES: u64 = 128 * 1024 * 1024;
const MAX_RESOLVER_BYTES: usize = 8192;

#[derive(Debug, Clone, Copy, Eq, PartialEq)]
pub enum Rejected {
    Scope,
    SourceIdentity,
    ExecutableRole,
    ExecutableSize,
    Interpreter,
    User,
    HttpsTarget,
    ResolverOutput,
    FirefoxComponent,
}

/// The selected runtime's declared inputs, not evidence that files were opened.
/// Matching these fields never creates a sealed executable or live authority.
#[derive(Debug)]
pub struct RoleDeclaration<'a> {
    pub scope: &'a str,
    pub source_system_sha256: &'a str,
    pub source_path: &'a str,
    pub cmd_sha256: &'a str,
    pub cmd_bytes: u64,
    pub interpreter: &'a str,
}

fn digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

impl RoleDeclaration<'_> {
    /// Check this role against the selected source metadata. The native owner
    /// must separately verify the full original bytes, FD custody and mappings.
    pub fn validate(&self, selected_system_sha256: &str) -> Result<(), Rejected> {
        if self.scope != SCOPE {
            return Err(Rejected::Scope);
        }
        if !digest(selected_system_sha256)
            || self.source_system_sha256 != selected_system_sha256
            || !digest(self.cmd_sha256)
        {
            return Err(Rejected::SourceIdentity);
        }
        if self.source_path != SOURCE_EXECUTABLE {
            return Err(Rejected::ExecutableRole);
        }
        if self.cmd_bytes == 0 || self.cmd_bytes > MAX_EXECUTABLE_BYTES {
            return Err(Rejected::ExecutableSize);
        }
        if self.interpreter != "/system/bin/linker64"
            && self.interpreter != "/apex/com.android.runtime/bin/linker64"
        {
            return Err(Rejected::Interpreter);
        }
        Ok(())
    }
}

/// A checked Android user number; the UID must still be read from actual PM.
#[derive(Debug, Clone, Copy, Eq, PartialEq)]
pub struct AndroidUser(u32);

impl AndroidUser {
    pub fn new(value: u32) -> Result<Self, Rejected> {
        if value > 21_474 {
            Err(Rejected::User)
        } else {
            Ok(Self(value))
        }
    }
}

/// Finite HTTPS scheme, authority and byte-shape checks, not a complete URI
/// parser. Neither public reachability nor fixture approval is inferred from
/// this type. The owner must bind the exact URI to its reviewed plan before
/// selecting any action capability.
#[derive(Debug)]
pub struct HttpsTarget(String);

fn port_valid(port: &str) -> bool {
    !port.is_empty()
        && port.len() <= 5
        && port.bytes().all(|b| b.is_ascii_digit())
        && port.parse::<u16>().is_ok()
}

fn authority_valid(authority: &str) -> bool {
    if authority.is_empty() || authority.contains('@') || authority.contains('\\') {
        return false;
    }
    if let Some(bracketed) = authority.strip_prefix('[') {
        let Some((address, suffix)) = bracketed.split_once(']') else {
            return false;
        };
        return address.parse::<std::net::Ipv6Addr>().is_ok()
            && (suffix.is_empty() || suffix.strip_prefix(':').is_some_and(port_valid));
    }
    let host = if let Some((host, port)) = authority.split_once(':') {
        if !port_valid(port) {
            return false;
        }
        host
    } else {
        authority
    };
    if host.is_empty() || host.len() > 253 {
        return false;
    }
    if host.bytes().all(|b| b.is_ascii_digit() || b == b'.') {
        return host.parse::<std::net::Ipv4Addr>().is_ok();
    }
    let name = host.strip_suffix('.').unwrap_or(host);
    name.split('.').all(|label| {
        !label.is_empty()
            && label.len() <= 63
            && label.as_bytes()[0].is_ascii_alphanumeric()
            && label.as_bytes()[label.len() - 1].is_ascii_alphanumeric()
            && label
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'-')
    })
}

impl HttpsTarget {
    pub fn parse(url: &str) -> Result<Self, Rejected> {
        let Some(rest) = url.strip_prefix("https://") else {
            return Err(Rejected::HttpsTarget);
        };
        let authority = rest.split(['/', '?', '#']).next().unwrap_or("");
        if url.len() > 4096
            || !url.is_ascii()
            || url
                .bytes()
                .any(|b| b.is_ascii_control() || b.is_ascii_whitespace())
            || !authority_valid(authority)
        {
            return Err(Rejected::HttpsTarget);
        }
        Ok(Self(url.to_owned()))
    }
}

/// The only two supported operations. Neither permits caller-provided argv.
#[derive(Debug, Clone, Copy, Eq, PartialEq)]
pub enum Stage {
    ResolveHttps,
    StartResolvedHttps,
}

/// Literal command data for a future, separately admitted action worker.
/// It has no process API and is never a replacement for a ReadyTreeWitness.
#[derive(Debug)]
pub struct CommandPlan {
    stage: Stage,
    argv: Vec<String>,
}

impl CommandPlan {
    pub fn stage(&self) -> Stage {
        self.stage
    }

    pub fn argv(&self) -> &[String] {
        &self.argv
    }
}

/// One immutable user/URI pairing. The native adapter must carry the same
/// actual package/framework observation across both commands and after start.
#[derive(Debug)]
pub struct BrowserPlan {
    user: AndroidUser,
    target: HttpsTarget,
}

/// One resolver result bound by borrow to the original user/URI plan. A start
/// consumes this value, preventing accidental replay through this instance.
/// This linear shape is not proof that a runtime action happened only once.
#[derive(Debug)]
pub struct Resolution<'a> {
    plan: &'a BrowserPlan,
    component: String,
}

fn component_valid(component: &str) -> bool {
    let Some((owner, activity)) = component.split_once('/') else {
        return false;
    };
    let class = activity.strip_prefix('.').unwrap_or(activity);
    owner == PACKAGE
        && !class.is_empty()
        && class.split('.').all(|part| {
            !part.is_empty()
                && part
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'$'))
        })
}

impl BrowserPlan {
    pub fn new(user: AndroidUser, target: HttpsTarget) -> Self {
        Self { user, target }
    }

    fn intent_tail(&self, argv: &mut Vec<String>) {
        argv.extend([
            "-a".to_owned(),
            "android.intent.action.VIEW".to_owned(),
            "-c".to_owned(),
            "android.intent.category.BROWSABLE".to_owned(),
            "-d".to_owned(),
            self.target.0.clone(),
        ]);
    }

    pub fn resolve(&self) -> CommandPlan {
        let mut argv = vec![
            SOURCE_EXECUTABLE.to_owned(),
            "package".to_owned(),
            "resolve-activity".to_owned(),
            "--brief".to_owned(),
            "--user".to_owned(),
            self.user.0.to_string(),
        ];
        self.intent_tail(&mut argv);
        CommandPlan {
            stage: Stage::ResolveHttps,
            argv,
        }
    }

    /// Parse bounded successful resolver stdout only. Transport exit status,
    /// stdout/stderr separation and real framework custody belong to the owner.
    /// No caller-supplied component constructor is exposed.
    pub fn resolved<'a>(&'a self, stdout: &str) -> Result<Resolution<'a>, Rejected> {
        if stdout.len() > MAX_RESOLVER_BYTES || stdout.contains('\0') {
            return Err(Rejected::ResolverOutput);
        }
        let mut components = stdout.lines().filter(|line| line.contains('/'));
        let component = components.next().ok_or(Rejected::ResolverOutput)?;
        if components.next().is_some() {
            return Err(Rejected::ResolverOutput);
        }
        if !component_valid(component) {
            return Err(Rejected::FirefoxComponent);
        }
        Ok(Resolution {
            plan: self,
            component: component.to_owned(),
        })
    }
}

impl Resolution<'_> {
    pub fn start(self) -> CommandPlan {
        let mut argv = vec![
            SOURCE_EXECUTABLE.to_owned(),
            "activity".to_owned(),
            "start-activity".to_owned(),
            "-W".to_owned(),
            "--user".to_owned(),
            self.plan.user.0.to_string(),
            "-n".to_owned(),
            self.component,
        ];
        self.plan.intent_tail(&mut argv);
        CommandPlan {
            stage: Stage::StartResolvedHttps,
            argv,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn plan(user: u32, url: &str) -> BrowserPlan {
        BrowserPlan::new(
            AndroidUser::new(user).unwrap(),
            HttpsTarget::parse(url).unwrap(),
        )
    }

    #[test]
    fn request_keeps_one_user_uri_and_the_resolved_component() {
        let uri = "https://example.com/fixture?q=one#section";
        let plan = plan(10, uri);
        assert_eq!(
            plan.resolve().argv(),
            [
                SOURCE_EXECUTABLE,
                "package",
                "resolve-activity",
                "--brief",
                "--user",
                "10",
                "-a",
                "android.intent.action.VIEW",
                "-c",
                "android.intent.category.BROWSABLE",
                "-d",
                uri
            ]
        );
        let resolution = plan
            .resolved("priority=0 match=0x208000\norg.mozilla.firefox/.LauncherAlias\n")
            .unwrap();
        let start = resolution.start();
        assert_eq!(start.stage(), Stage::StartResolvedHttps);
        assert_eq!(
            start.argv(),
            [
                SOURCE_EXECUTABLE,
                "activity",
                "start-activity",
                "-W",
                "--user",
                "10",
                "-n",
                "org.mozilla.firefox/.LauncherAlias",
                "-a",
                "android.intent.action.VIEW",
                "-c",
                "android.intent.category.BROWSABLE",
                "-d",
                uri
            ]
        );
    }

    #[test]
    fn malformed_or_foreign_components_cannot_create_start_plans() {
        let plan = plan(0, "https://example.com/");
        for output in [
            "",
            "No activity found",
            "org.example.browser/.Main",
            "org.mozilla.firefox/",
            "org.mozilla.firefox/.",
            "org.mozilla.firefox/..Main",
            "org.mozilla.firefox/.Main/Other",
            "org.mozilla.firefox/.Main --user 10",
            "org.mozilla.firefox/.Main\t",
            "org.mozilla.firefox/.Main\norg.mozilla.firefox/.Other",
            "org.mozilla.firefox/.Main\0",
        ] {
            assert!(plan.resolved(output).is_err(), "accepted {output:?}");
        }
        assert!(plan.resolved(&"x".repeat(MAX_RESOLVER_BYTES + 1)).is_err());
    }

    #[test]
    fn aliases_and_flattened_names_are_preserved_without_reinterpretation() {
        let plan = plan(0, "https://example.com/");
        for component in [
            "org.mozilla.firefox/.LauncherAlias",
            "org.mozilla.firefox/org.mozilla.fenix.IntentReceiverActivity",
            "org.mozilla.firefox/.Outer$Inner",
        ] {
            let start = plan.resolved(component).unwrap().start();
            assert_eq!(start.argv()[7], component);
        }
    }

    #[test]
    fn url_and_user_boundaries_reject_before_a_plan_exists() {
        assert!(AndroidUser::new(21_474).is_ok());
        assert_eq!(AndroidUser::new(21_475), Err(Rejected::User));
        assert_eq!(AndroidUser::new(u32::MAX), Err(Rejected::User));
        for url in [
            "http://example.com/",
            "https://user:secret@example.com/",
            "https:///empty",
            "https://example.com/\n",
            "https://example.com/\0",
            "https://example.com\\evil/",
            "https://例子.example/",
        ] {
            assert!(HttpsTarget::parse(url).is_err(), "accepted {url:?}");
        }
        assert!(HttpsTarget::parse(&format!("https://example.com/{}", "x".repeat(4096))).is_err());
    }

    #[test]
    fn shell_metacharacters_remain_one_literal_uri_argument() {
        let uri = "https://example.com/path?x=$(id);echo&y='quoted'";
        let plan = plan(0, uri);
        let start = plan.resolved("org.mozilla.firefox/.Main").unwrap().start();
        assert_eq!(start.argv().len(), 14);
        assert_eq!(start.argv().last().unwrap(), uri);
        assert_eq!(start.argv()[0], SOURCE_EXECUTABLE);
    }

    #[test]
    fn malformed_authorities_do_not_become_validated_targets() {
        for url in [
            "https://[]/",
            "https://:/",
            "https://example.com:bad/",
            "https://example.com:/",
            "https://example.com:65536/",
            "https://example.com:000443/",
            "https://-example.com/",
            "https://example-.com/",
            "https://example..com/",
            "https://[not-ipv6]/",
            "https://[::1/",
            "https://[::1]garbage/",
            "https://[::1]:bad/",
            "https://::1/",
            "https://256.0.0.1/",
            "https://127.0.0.1.2/",
        ] {
            assert!(HttpsTarget::parse(url).is_err(), "accepted {url:?}");
        }
        assert!(HttpsTarget::parse(&format!("https://{}.example/", "x".repeat(64))).is_err());
    }

    #[test]
    fn valid_authority_syntax_does_not_claim_public_reachability() {
        for url in [
            "https://example.com/",
            "https://example.com.:443/",
            "https://EXAMPLE.com:65535/",
            "https://localhost/",
            "https://127.0.0.1:443/",
            "https://[::1]/",
            "https://[2001:db8::1]:443/",
            "https://[::ffff:192.0.2.1]/",
        ] {
            assert!(HttpsTarget::parse(url).is_ok(), "rejected {url:?}");
        }
    }

    #[test]
    fn query_scope_and_other_executables_cannot_be_action_inputs() {
        let system = "a".repeat(64);
        let cmd = "b".repeat(64);
        let mut role = RoleDeclaration {
            scope: SCOPE,
            source_system_sha256: &system,
            source_path: SOURCE_EXECUTABLE,
            cmd_sha256: &cmd,
            cmd_bytes: 65536,
            interpreter: "/system/bin/linker64",
        };
        assert_eq!(role.validate(&system), Ok(()));
        role.scope = "fixed_application_query_v1";
        assert_eq!(role.validate(&system), Err(Rejected::Scope));
        role.scope = SCOPE;
        role.source_path = "/system/bin/toybox";
        assert_eq!(role.validate(&system), Err(Rejected::ExecutableRole));
        role.source_path = "/system/bin/sh";
        assert_eq!(role.validate(&system), Err(Rejected::ExecutableRole));
    }

    #[test]
    fn action_input_identity_size_and_interpreter_are_pinned() {
        let system = "a".repeat(64);
        let cmd = "b".repeat(64);
        let mut role = RoleDeclaration {
            scope: SCOPE,
            source_system_sha256: &system,
            source_path: SOURCE_EXECUTABLE,
            cmd_sha256: &cmd,
            cmd_bytes: 65536,
            interpreter: "/system/bin/linker64",
        };
        assert_eq!(
            role.validate(&"c".repeat(64)),
            Err(Rejected::SourceIdentity)
        );
        role.cmd_sha256 = "not-a-digest";
        assert_eq!(role.validate(&system), Err(Rejected::SourceIdentity));
        role.cmd_sha256 = &cmd;
        for size in [0, MAX_EXECUTABLE_BYTES + 1] {
            role.cmd_bytes = size;
            assert_eq!(role.validate(&system), Err(Rejected::ExecutableSize));
        }
        role.cmd_bytes = 65536;
        role.interpreter = "/data/local/tmp/linker64";
        assert_eq!(role.validate(&system), Err(Rejected::Interpreter));
        role.interpreter = "/apex/com.android.runtime/bin/linker64";
        assert_eq!(role.validate(&system), Ok(()));
    }
}

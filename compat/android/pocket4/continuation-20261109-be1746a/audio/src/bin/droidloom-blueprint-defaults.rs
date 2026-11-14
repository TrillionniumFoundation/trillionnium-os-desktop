//! Read-only diagnostics for literal defaults edges over an explicit Blueprint
//! discovery list. This is deliberately not a Soong graph qualification: module
//! variants, namespaces, load hooks and nonliteral expressions still require
//! the ordinary build. Inspect every discovered module, including modules that
//! are outside the requested target's transitive build closure.

#![forbid(unsafe_code)]

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Component, PathBuf};

#[derive(Clone, Debug, PartialEq, Eq)]
enum Token { Word(String), String(String), Punct(char) }
#[derive(Clone, Debug)]
struct Located { token: Token, line: usize }

fn lex(text: &str) -> Result<Vec<Located>, String> {
    let chars: Vec<char> = text.chars().collect();
    let (mut i, mut line) = (0, 1);
    let mut result = Vec::new();
    while i < chars.len() {
        let c = chars[i];
        if c.is_whitespace() { line += usize::from(c == '\n'); i += 1; continue; }
        if c == '/' && chars.get(i + 1) == Some(&'/') {
            i += 2; while i < chars.len() && chars[i] != '\n' { i += 1; } continue;
        }
        if c == '/' && chars.get(i + 1) == Some(&'*') {
            i += 2; let start = line;
            while i + 1 < chars.len() && !(chars[i] == '*' && chars[i + 1] == '/') {
                line += usize::from(chars[i] == '\n'); i += 1;
            }
            if i + 1 >= chars.len() { return Err(format!("unterminated comment at line {start}")); }
            i += 2; continue;
        }
        if c == '"' {
            let start = line; i += 1; let mut value = String::new(); let mut closed = false;
            while i < chars.len() {
                match chars[i] {
                    '"' => { closed = true; i += 1; break; }
                    '\\' => {
                        i += 1;
                        let escaped = chars.get(i).ok_or_else(|| format!("incomplete string at line {start}"))?;
                        value.push(match escaped {
                            '"' => '"', '\\' => '\\', 'n' => '\n', 'r' => '\r', 't' => '\t',
                            _ => return Err(format!("unsupported string escape at line {line}")),
                        });
                    }
                    '\n' | '\r' => return Err(format!("newline in quoted string at line {start}")),
                    other => value.push(other),
                }
                i += 1;
            }
            if !closed { return Err(format!("unterminated string at line {start}")); }
            result.push(Located { token: Token::String(value), line: start }); continue;
        }
        if c.is_alphanumeric() || c == '_' {
            let start = i;
            while i < chars.len() && (chars[i].is_alphanumeric() || chars[i] == '_') { i += 1; }
            result.push(Located { token: Token::Word(chars[start..i].iter().collect()), line });
        } else {
            result.push(Located { token: Token::Punct(c), line }); i += 1;
        }
    }
    Ok(result)
}

fn punct(tokens: &[Located], i: usize, c: char) -> bool {
    tokens.get(i).is_some_and(|t| t.token == Token::Punct(c))
}

fn matching(tokens: &[Located], start: usize) -> Result<usize, String> {
    let mut stack = Vec::new();
    for (i, item) in tokens.iter().enumerate().skip(start) {
        if let Token::Punct(c) = item.token {
            match c {
                '{' => stack.push('}'), '[' => stack.push(']'), '(' => stack.push(')'),
                '}' | ']' | ')' => {
                    if stack.pop() != Some(c) { return Err(format!("unbalanced delimiter at line {}", item.line)); }
                    if stack.is_empty() { return Ok(i); }
                }
                _ => {}
            }
        }
    }
    Err(format!("unclosed delimiter at line {}", tokens[start].line))
}

#[derive(Clone, Debug)]
struct Module {
    kind: String,
    name: Option<String>,
    line: usize,
    defaults: Vec<(String, usize)>,
    unknown: Vec<String>,
}

fn literal_list(tokens: &[Located]) -> Option<Vec<String>> {
    if !punct(tokens, 0, '[') || !punct(tokens, tokens.len().checked_sub(1)?, ']') { return None; }
    let mut values = Vec::new(); let mut want_value = true;
    for t in &tokens[1..tokens.len()-1] {
        match (&t.token, want_value) {
            (Token::String(s), true) => { values.push(s.clone()); want_value = false; }
            (Token::Punct(','), false) => want_value = true,
            _ => return None,
        }
    }
    Some(values)
}

fn parse(text: &str) -> Result<Vec<Module>, String> {
    let tokens = lex(text)?; let mut modules = Vec::new(); let mut i = 0;
    while i < tokens.len() {
        // A top-level assignment can contain maps, strings or functions. It is
        // not a module declaration; balanced objects are skipped as objects.
        let kind = match &tokens[i].token {
            Token::Word(word) if punct(&tokens, i + 1, '{') => Some(word.clone()),
            _ => None,
        };
        if let Some(kind) = kind {
            let end = matching(&tokens, i + 1)?;
            let mut module = Module { kind, name: None, line: tokens[i].line,
                defaults: Vec::new(), unknown: Vec::new() };
            let mut j = i + 2;
            while j < end {
                if punct(&tokens, j, ',') { j += 1; continue; }
                let property = match &tokens[j].token {
                    Token::Word(word) if punct(&tokens, j + 1, ':') => word.clone(),
                    _ => return Err(format!("expected property at line {}", tokens[j].line)),
                };
                let property_line = tokens[j].line; let start = j + 2; j = start;
                while j < end && !punct(&tokens, j, ',') {
                    if punct(&tokens, j, '{') || punct(&tokens, j, '[') || punct(&tokens, j, '(') {
                        j = matching(&tokens, j)? + 1;
                    } else { j += 1; }
                }
                let value = &tokens[start..j];
                if property == "name" {
                    if let [Located { token: Token::String(s), .. }] = value { module.name = Some(s.clone()); }
                    else { module.unknown.push(format!("nonliteral name at line {property_line}")); }
                }
                if property == "defaults" {
                    match literal_list(value) {
                        Some(names) => module.defaults.extend(names.into_iter().map(|n| (n, property_line))),
                        None => module.unknown.push(format!("nonliteral defaults at line {property_line}")),
                    }
                }
            }
            modules.push(module); i = end + 1;
        } else if punct(&tokens, i, '{') || punct(&tokens, i, '[') || punct(&tokens, i, '(') {
            i = matching(&tokens, i)? + 1;
        } else { i += 1; }
    }
    Ok(modules)
}

#[derive(Debug, PartialEq, Eq)]
struct Missing { file: String, module: String, defaults: String, line: usize }
#[derive(Default, Debug)]
struct Audit {
    files: usize, modules: usize, edges: usize,
    missing: Vec<Missing>, unsupported: Vec<(String, String)>,
    duplicate_names: usize,
}

fn audit(inputs: &[(String, String)]) -> Audit {
    let mut result = Audit::default(); let mut parsed = Vec::new();
    let mut names: BTreeMap<String, usize> = BTreeMap::new();
    for (path, text) in inputs {
        result.files += 1;
        match parse(text) {
            Ok(modules) => {
                result.modules += modules.len();
                for m in &modules {
                    if let Some(name) = &m.name { *names.entry(name.clone()).or_default() += 1; }
                    for unknown in &m.unknown { result.unsupported.push((path.clone(), unknown.clone())); }
                }
                parsed.push((path, modules));
            }
            Err(error) => result.unsupported.push((path.clone(), error)),
        }
    }
    result.duplicate_names = names.values().filter(|n| **n > 1).count();
    for (path, modules) in parsed {
        for m in modules {
            for (default, line) in m.defaults {
                result.edges += 1;
                // Presence is only a global literal symbol check. It does not
                // establish type/namespace/variant compatibility.
                if !names.contains_key(&default) {
                    result.missing.push(Missing { file: path.clone(),
                        module: m.name.clone().unwrap_or_else(|| format!("{}@{}", m.kind, m.line)),
                        defaults: default, line });
                }
            }
        }
    }
    result
}

fn quote(text: &str) -> String {
    let mut out = String::from("\"");
    for c in text.chars() { match c {
        '"' => out.push_str("\\\""), '\\' => out.push_str("\\\\"),
        '\n' => out.push_str("\\n"), '\r' => out.push_str("\\r"), '\t' => out.push_str("\\t"),
        c if c < ' ' => out.push_str(&format!("\\u{:04x}", c as u32)),
        c => out.push(c),
    } }
    out.push('"'); out
}

fn report(result: &Audit) -> String {
    let missing: Vec<_> = result.missing.iter().map(|m| format!(
        "{{\"file\":{},\"module\":{},\"defaults\":{},\"line\":{}}}",
        quote(&m.file), quote(&m.module), quote(&m.defaults), m.line)).collect();
    let unsupported: Vec<_> = result.unsupported.iter().map(|(p,e)| format!(
        "{{\"file\":{},\"reason\":{}}}", quote(p), quote(e))).collect();
    format!("{{\"schema\":\"droidloom-blueprint-literal-defaults-audit-v1\",\"graph_qualified\":false,\"coverage\":\"all listed modules; literal direct defaults only; no Soong namespace, variant or load-hook resolution\",\"files\":{},\"modules\":{},\"literal_defaults_edges\":{},\"duplicate_literal_names\":{},\"missing_default_candidates\":[{}],\"unsupported\":[{}]}}",
        result.files, result.modules, result.edges, result.duplicate_names,
        missing.join(","), unsupported.join(","))
}

fn run() -> Result<bool, String> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 2 { return Err("usage: droidloom-blueprint-defaults SOURCE_ROOT ANDROID_BP_LIST".into()); }
    let root = fs::canonicalize(&args[0]).map_err(|e| e.to_string())?;
    let list = fs::read_to_string(&args[1]).map_err(|e| e.to_string())?;
    let mut paths = BTreeSet::new(); let mut inputs = Vec::new();
    for line in list.lines() {
        let relative = PathBuf::from(line);
        if line.is_empty() || relative.components().any(|p| !matches!(p, Component::Normal(_)))
            || relative.extension() != Some(std::ffi::OsStr::new("bp")) {
            return Err(format!("invalid Blueprint list entry: {line:?}"));
        }
        if !paths.insert(relative.clone()) { return Err(format!("duplicate Blueprint list entry: {line}")); }
        let resolved = fs::canonicalize(root.join(&relative)).map_err(|e| format!("{line}: {e}"))?;
        if !resolved.starts_with(&root) { return Err(format!("Blueprint outside source root: {line}")); }
        let content = fs::read_to_string(&resolved).map_err(|e| format!("{line}: {e}"))?;
        inputs.push((line.to_owned(), content));
    }
    if inputs.is_empty() { return Err("empty Blueprint discovery list".into()); }
    let result = audit(&inputs); println!("{}", report(&result));
    Ok(result.missing.is_empty() && result.unsupported.is_empty())
}

fn main() {
    match run() {
        Ok(true) => {}, // No literal blocker found; graph_qualified remains false.
        Ok(false) => std::process::exit(2),
        Err(error) => { eprintln!("droidloom-blueprint-defaults: {error}"); std::process::exit(1); }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const CONSUMER: &str = include_str!("../../tests/fixtures/blueprint-defaults/r9-pasit-consumer.bp");
    const PROVIDER: &str = include_str!("../../tests/fixtures/blueprint-defaults/r9-pasit-provider.bp");
    fn inputs(xs: &[(&str, &str)]) -> Vec<(String, String)> {
        xs.iter().map(|(p,t)| (p.to_string(), t.to_string())).collect()
    }
    #[test]
    fn actual_r9_unrelated_discovered_module_is_still_checked() {
        let r = audit(&inputs(&[("platform_testing/desktop-mobly.bp", CONSUMER),
            ("audio/Android.bp", "apex { name: \"com.android.hardware.audio.droidloom\", }")]));
        assert_eq!(r.missing.len(), 1);
        assert_eq!(r.missing[0].module, "DesktopTestLibTestsMobly");
        assert_eq!(r.missing[0].defaults, "PASIT-defaults");
        assert_eq!(r.missing[0].line, 21);
    }
    #[test]
    fn actual_original_pasit_provider_resolves_the_r9_literal_edge() {
        let r = audit(&inputs(&[("consumer.bp", CONSUMER), ("provider.bp", PROVIDER)]));
        assert!(r.missing.iter().all(|e| e.defaults != "PASIT-defaults"));
        assert!(report(&r).contains("\"graph_qualified\":false"));
    }
    #[test]
    fn comments_and_strings_do_not_supply_a_provider() {
        let fake = "// cc_defaults { name: \"PASIT-defaults\", }\n/* name: \"PASIT-defaults\" */\nfilegroup { name: \"other\", srcs: [\"name: \\\"PASIT-defaults\\\"\"], }";
        let r = audit(&inputs(&[("consumer.bp", CONSUMER), ("comments.bp", fake)]));
        assert_eq!(r.missing.len(), 1);
    }
    #[test]
    fn defaults_outside_selected_target_and_transitive_defaults_are_inspected() {
        let r = audit(&inputs(&[("all.bp", "cc_library { name: \"target\", } python_test_host { name: \"unrelated\", defaults: [\"a\"], } python_defaults { name: \"a\", defaults: [\"missing-b\"], }")]));
        assert_eq!(r.missing.len(), 1); assert_eq!(r.missing[0].defaults, "missing-b");
    }
    #[test]
    fn nonliteral_defaults_are_explicitly_unresolved() {
        let r = audit(&inputs(&[("variables.bp", "D = [\"foo\"]\ncc_library { name: \"x\", defaults: D + [\"bar\"], }")]));
        assert!(r.missing.is_empty()); assert_eq!(r.unsupported.len(), 1);
        assert!(r.unsupported[0].1.contains("nonliteral defaults"));
    }
    #[test]
    fn malformed_input_is_never_a_clean_result() {
        for text in ["cc_library { name: \"x\",", "/*", "/* unfinished", "cc_library { name: \"x", "cc_library { name: \"x\", defaults: [\"a\"), }"] {
            assert!(!audit(&inputs(&[("bad.bp", text)])).unsupported.is_empty());
        }
    }
    #[test]
    fn empty_and_trailing_comma_lists_and_nested_maps_are_parsed() {
        let r = audit(&inputs(&[("ok.bp", "cc_defaults { name: \"a\", defaults: [], } cc_library { name: \"b\", target: { host: { enabled: true, }, }, defaults: [\"a\",], }")]));
        assert!(r.missing.is_empty()); assert!(r.unsupported.is_empty()); assert_eq!(r.edges, 1);
    }
}

//! HTTP callback policy for the source qualification embedder.
//! A default gate has no admitted resources. The only constructor that admits
//! bytes retains a real, already bound fixture listener; it grants no network
//! continuation and no filesystem path lookup.

use std::io;
use std::net::{Ipv4Addr, SocketAddr, TcpListener};

pub const MAX_FIXTURE_BYTES: usize = 16 * 1024;
pub const MAX_REQUEST_URL_BYTES: usize = 2048;
pub const MAX_CALLBACKS_PER_GENERATION: u32 = 64;
pub const QUALIFICATION_CSP: &str = "default-src 'none'; style-src 'unsafe-inline'; script-src 'self' 'unsafe-inline' https://resource-denied.invalid; connect-src 'self'; worker-src 'self'; img-src 'none'; media-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Denial {
    NoWebView,
    StaleOrWithdrawn,
    Closed,
    FixtureCustody,
    RequestShape,
    Method,
    Target,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Decision {
    LocalFixture(&'static [u8]),
    Cancel(Denial),
}

#[derive(Clone, Copy)]
pub struct Context {
    pub callback_generation: Option<u32>,
    pub current_generation: u32,
    pub active_owned_webview: bool,
}

pub struct Request<'a> {
    /// The exact serialized Url supplied by Servo, already parsed by Servo.
    pub canonical_url: &'a str,
    pub method: &'a str,
    pub is_for_main_frame: bool,
    pub is_redirect: bool,
}

struct QualificationFixture {
    listener: TcpListener,
    address: SocketAddr,
    origin: String,
    bytes: &'static [u8],
}

#[derive(Default)]
pub struct ResourceGate {
    fixture: Option<QualificationFixture>,
}

impl ResourceGate {
    pub fn for_owned_fixture(listener: &TcpListener, bytes: &'static [u8]) -> io::Result<Self> {
        let address = listener.local_addr()?;
        if !matches!(address, SocketAddr::V4(value) if *value.ip() == Ipv4Addr::LOCALHOST && value.port() != 0)
            || bytes.is_empty()
            || bytes.len() > MAX_FIXTURE_BYTES
        {
            return Err(io::Error::other("invalid owned qualification fixture"));
        }
        Ok(Self {
            fixture: Some(QualificationFixture {
                listener: listener.try_clone()?,
                address,
                origin: format!("http://127.0.0.1:{}", address.port()),
                bytes,
            }),
        })
    }

    pub fn decide(&self, context: Context, request: Request<'_>) -> Decision {
        let Some(generation) = context.callback_generation else {
            return Decision::Cancel(Denial::NoWebView);
        };
        if !context.active_owned_webview
            || generation != context.current_generation
            || !matches!(generation, 1 | 2)
        {
            return Decision::Cancel(Denial::StaleOrWithdrawn);
        }
        let Some(fixture) = &self.fixture else {
            return Decision::Cancel(Denial::Closed);
        };
        if fixture.listener.local_addr().ok() != Some(fixture.address) {
            return Decision::Cancel(Denial::FixtureCustody);
        }
        if request.canonical_url.len() > MAX_REQUEST_URL_BYTES
            || request.is_redirect
            || !request.is_for_main_frame
        {
            return Decision::Cancel(Denial::RequestShape);
        }
        if request.method != "GET" {
            return Decision::Cancel(Denial::Method);
        }
        let target = format!("{}/?generation={generation}", fixture.origin);
        if request.canonical_url != target {
            return Decision::Cancel(Denial::Target);
        }
        Decision::LocalFixture(fixture.bytes)
    }

    pub fn origin(&self) -> Option<&str> {
        self.fixture.as_ref().map(|fixture| fixture.origin.as_str())
    }

    pub fn probe(&self, generation: u32, url: &str, method: &str) -> Option<Probe> {
        let origin = self.origin()?;
        if method == "GET" && url == format!("{origin}/blocked-script.js?generation={generation}") {
            Some(Probe::SameOriginScript)
        } else if method == "POST" && url == format!("{origin}/?generation={generation}") {
            Some(Probe::WrongMethodFetch)
        } else if method == "GET"
            && url
                == format!(
                    "https://resource-denied.invalid/blocked-script.js?generation={generation}"
                )
        {
            Some(Probe::ExternalScript)
        } else {
            None
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Probe {
    SameOriginScript,
    WrongMethodFetch,
    ExternalScript,
}

#[derive(Clone, Copy, Default)]
pub struct GenerationFacts {
    pub callbacks: u32,
    pub local_response_finishes: u32,
    pub cancel_submissions: u32,
    pub same_origin_script_cancels: u32,
    pub wrong_method_fetch_cancels: u32,
    pub external_script_cancels: u32,
}

impl GenerationFacts {
    pub fn probes_observed(&self) -> bool {
        self.local_response_finishes > 0
            && self.same_origin_script_cancels > 0
            && self.wrong_method_fetch_cancels > 0
            && self.external_script_cancels > 0
    }
}

#[derive(Default)]
pub struct Observations {
    pub generations: [GenerationFacts; 2],
    pub global_cancel_submissions: u32,
    pub stale_cancel_submissions: u32,
    pub exceeded_bound: bool,
}

impl Observations {
    pub fn finish_local(&mut self, generation: u32) {
        if let Some(facts) = self.generation(generation) {
            facts.callbacks += 1;
            facts.local_response_finishes += 1;
        }
    }

    pub fn cancel(&mut self, generation: Option<u32>, denial: Denial, probe: Option<Probe>) {
        if generation.is_none() {
            self.global_cancel_submissions = self.global_cancel_submissions.saturating_add(1);
            self.exceeded_bound |= self.global_cancel_submissions > MAX_CALLBACKS_PER_GENERATION;
        } else if denial == Denial::StaleOrWithdrawn {
            self.stale_cancel_submissions = self.stale_cancel_submissions.saturating_add(1);
            self.exceeded_bound |= self.stale_cancel_submissions > MAX_CALLBACKS_PER_GENERATION;
        } else if let Some(facts) = self.generation(generation.unwrap()) {
            facts.callbacks += 1;
            facts.cancel_submissions += 1;
            match probe {
                Some(Probe::SameOriginScript) => facts.same_origin_script_cancels += 1,
                Some(Probe::WrongMethodFetch) => facts.wrong_method_fetch_cancels += 1,
                Some(Probe::ExternalScript) => facts.external_script_cancels += 1,
                None => {}
            }
        }
    }

    fn generation(&mut self, generation: u32) -> Option<&mut GenerationFacts> {
        let index = generation.checked_sub(1)? as usize;
        let facts = self.generations.get_mut(index)?;
        if facts.callbacks >= MAX_CALLBACKS_PER_GENERATION {
            self.exceeded_bound = true;
            return None;
        }
        Some(facts)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const BODY: &[u8] = b"immutable qualification bytes";

    fn owned() -> (TcpListener, ResourceGate) {
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        let gate = ResourceGate::for_owned_fixture(&listener, BODY).unwrap();
        (listener, gate)
    }

    fn context(generation: u32) -> Context {
        Context {
            callback_generation: Some(generation),
            current_generation: generation,
            active_owned_webview: true,
        }
    }

    fn request(url: &str) -> Request<'_> {
        Request {
            canonical_url: url,
            method: "GET",
            is_for_main_frame: true,
            is_redirect: false,
        }
    }

    #[test]
    fn default_has_no_resource_authority() {
        let gate = ResourceGate::default();
        assert_eq!(
            gate.decide(context(1), request("https://app.invalid/")),
            Decision::Cancel(Denial::Closed)
        );
    }

    #[test]
    fn immutable_exact_target_for_each_current_generation() {
        let (listener, gate) = owned();
        let origin = gate.origin().unwrap().to_owned();
        drop(listener);
        for generation in [1, 2] {
            let url = format!("{origin}/?generation={generation}");
            assert_eq!(
                gate.decide(context(generation), request(&url)),
                Decision::LocalFixture(BODY)
            );
        }
    }

    #[test]
    fn actual_retained_listener_keeps_exclusive_origin_owned() {
        let (listener, gate) = owned();
        let address = listener.local_addr().unwrap();
        drop(listener);
        assert!(TcpListener::bind(address).is_err());
        drop(gate);
        assert!(TcpListener::bind(address).is_ok());
    }

    #[test]
    fn origin_alias_userinfo_port_path_query_fragment_and_encoded_collisions_refuse() {
        let (_listener, gate) = owned();
        let origin = gate.origin().unwrap();
        let port = origin.rsplit(':').next().unwrap();
        let urls = [
            format!("http://localhost:{port}/?generation=1"),
            format!("https://127.0.0.1:{port}/?generation=1"),
            format!("http://user@127.0.0.1:{port}/?generation=1"),
            "http://127.0.0.1:1/?generation=1".into(),
            format!("{origin}/index.html?generation=1"),
            format!("{origin}/%2f?generation=1"),
            format!("{origin}/?generation=01"),
            format!("{origin}/?generation=1&extra=1"),
            format!("{origin}/?generation=2"),
            format!("{origin}/?generation=1#fragment"),
        ];
        for url in urls {
            assert_eq!(
                gate.decide(context(1), request(&url)),
                Decision::Cancel(Denial::Target),
                "{url}"
            );
        }
    }

    #[test]
    fn methods_subresources_redirects_and_oversized_urls_refuse() {
        let (_listener, gate) = owned();
        let url = format!("{}/?generation=1", gate.origin().unwrap());
        for method in ["HEAD", "POST", "OPTIONS", "get", "GET "] {
            let mut request = request(&url);
            request.method = method;
            assert_eq!(
                gate.decide(context(1), request),
                Decision::Cancel(Denial::Method)
            );
        }
        let mut subresource = request(&url);
        subresource.is_for_main_frame = false;
        assert_eq!(
            gate.decide(context(1), subresource),
            Decision::Cancel(Denial::RequestShape)
        );
        let mut redirect = request(&url);
        redirect.is_redirect = true;
        assert_eq!(
            gate.decide(context(1), redirect),
            Decision::Cancel(Denial::RequestShape)
        );
        assert_eq!(
            gate.decide(context(1), request(&"x".repeat(MAX_REQUEST_URL_BYTES + 1))),
            Decision::Cancel(Denial::RequestShape)
        );
    }

    #[test]
    fn global_stale_latched_and_unknown_generations_never_obtain_bytes() {
        let (_listener, gate) = owned();
        let url = format!("{}/?generation=1", gate.origin().unwrap());
        let mut global = context(1);
        global.callback_generation = None;
        assert_eq!(
            gate.decide(global, request(&url)),
            Decision::Cancel(Denial::NoWebView)
        );
        let mut stale = context(1);
        stale.current_generation = 2;
        assert_eq!(
            gate.decide(stale, request(&url)),
            Decision::Cancel(Denial::StaleOrWithdrawn)
        );
        let mut withdrawn = context(1);
        withdrawn.active_owned_webview = false;
        assert_eq!(
            gate.decide(withdrawn, request(&url)),
            Decision::Cancel(Denial::StaleOrWithdrawn)
        );
        for generation in [0, 3, u32::MAX] {
            assert_eq!(
                gate.decide(context(generation), request(&url)),
                Decision::Cancel(Denial::StaleOrWithdrawn)
            );
        }
    }

    #[test]
    fn wildcard_listener_and_unbounded_bytes_cannot_create_fixture() {
        let wildcard = TcpListener::bind((Ipv4Addr::UNSPECIFIED, 0)).unwrap();
        assert!(ResourceGate::for_owned_fixture(&wildcard, BODY).is_err());
        let loopback = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        assert!(ResourceGate::for_owned_fixture(&loopback, b"").is_err());
        static BIG: [u8; MAX_FIXTURE_BYTES + 1] = [0; MAX_FIXTURE_BYTES + 1];
        assert!(ResourceGate::for_owned_fixture(&loopback, &BIG).is_err());
    }

    #[test]
    fn observations_are_bounded_and_unknown_does_not_forge_probe_execution() {
        let mut observations = Observations::default();
        observations.finish_local(1);
        observations.cancel(Some(1), Denial::Target, None);
        assert!(!observations.generations[0].probes_observed());
        for probe in [
            Probe::SameOriginScript,
            Probe::WrongMethodFetch,
            Probe::ExternalScript,
        ] {
            observations.cancel(Some(1), Denial::Target, Some(probe));
        }
        assert!(observations.generations[0].probes_observed());
        assert!(!observations.generations[1].probes_observed());
        for _ in 0..MAX_CALLBACKS_PER_GENERATION {
            observations.cancel(Some(1), Denial::Target, None);
        }
        assert!(observations.exceeded_bound);
        assert_eq!(
            observations.generations[0].callbacks,
            MAX_CALLBACKS_PER_GENERATION
        );
    }
}

macro_rules! info {
    ($($arg:tt)*) => { eprintln!("[info] {}", format_args!($($arg)*)); };
}
mod error;
mod config {
    pub mod scheme {
        #[derive(Clone, Debug)]
        pub(crate) struct DaemonScheme {
            pub(crate) path: std::path::PathBuf,
            pub(crate) args: Vec<String>,
        }
    }
}
mod daemon;
fn main() {
    let args: Vec<String> = std::env::args().collect();
    assert_eq!(args.len(), 7, "mode python roles_script event_fd nonce workdir");
    let scheme = config::scheme::DaemonScheme {
        path: args[2].clone().into(),
        args: vec![args[3].clone(), "leader".into(), args[1].clone(), args[4].clone(), args[5].clone()],
    };
    let daemons = [scheme];
    let signal = daemon::SignalGuard::install().expect("original SignalGuard install");
    let began = std::time::Instant::now();
    let mut supervisor = match daemon::DaemonSupervisor::start(&daemons, std::path::Path::new(&args[6]), &signal) {
        Ok(supervisor) => supervisor,
        Err(errno) => {
            println!("{{\"event\":\"startup_error\",\"errno\":{},\"elapsed_ms\":{}}}", errno as i32, began.elapsed().as_millis());
            return;
        }
    };
    println!("{{\"event\":\"start_returned\",\"elapsed_ms\":{}}}", began.elapsed().as_millis());
    let stop_began = std::time::Instant::now();
    if args[1] == "drop_only" {
        drop(supervisor);
        println!("{{\"event\":\"drop_returned\",\"elapsed_ms\":{}}}", stop_began.elapsed().as_millis());
        return;
    }
    supervisor.stop_all();
    println!("{{\"event\":\"stop_returned\",\"elapsed_ms\":{}}}", stop_began.elapsed().as_millis());
    drop(supervisor);
    println!("{{\"event\":\"supervisor_dropped\"}}");
}

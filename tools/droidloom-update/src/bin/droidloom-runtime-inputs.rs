//! Build a pre-init runtime input image from explicitly pinned original bytes.
//! This tool neither installs a selection nor grants execution or Android Ready.
#[path = "../runtime_inputs/activation.rs"]
mod activation;
#[path = "../../../../runtime/droidloom-supervisor/src/production_apex_input_profile.rs"]
mod apex_inputs;
#[path = "../runtime_inputs/contract.rs"]
mod contract;
#[path = "../runtime_inputs/image.rs"]
mod image;
#[path = "../runtime_inputs/io.rs"]
mod io;
#[path = "../runtime_inputs/native.rs"]
mod native;
#[path = "../runtime_inputs/produce.rs"]
mod produce;
#[path = "../runtime_inputs/query.rs"]
mod query;

use clap::Parser;
use std::path::PathBuf;

pub(crate) type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
pub(crate) fn require(value: bool, message: impl Into<String>) -> Result<()> {
    if value {
        Ok(())
    } else {
        Err(message.into().into())
    }
}

#[derive(Parser)]
#[command(about = "Create a verified pre-init runtime image; never install or start it")]
struct Arguments {
    /// Complete explicitly reviewed build-plan file.
    #[arg(long)]
    plan: PathBuf,
    /// SHA-256 of every byte of that plan.
    #[arg(long)]
    plan_sha256: String,
    /// New output directory; an existing destination is always refused.
    #[arg(long)]
    output: PathBuf,
}

fn main() {
    let args = Arguments::parse();
    if let Err(error) = produce::run(&args.plan, &args.plan_sha256, &args.output) {
        eprintln!("runtime input generation failed; outputs are unqualified: {error}");
        std::process::exit(1);
    }
}

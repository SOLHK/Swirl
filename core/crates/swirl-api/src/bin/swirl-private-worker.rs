//! Dedicated synthetic QA endpoint. No ordinary product control flag enables it.
fn main() {
    let arguments: Vec<_> = std::env::args().skip(1).collect();
    if arguments == ["--build-info"] {
        println!("{}", swirl_api::private_worker::identity());
        return;
    }
    if arguments != ["--internal-private-acceptance-worker"] {
        eprintln!("PrivateWorkerArguments");
        std::process::exit(2);
    }
    if let Err(code) = swirl_api::private_worker::run() {
        // The worker accepts no private node/provider configuration. Still never
        // print input, endpoint, challenge, arbitrary OS errors or parsed plans.
        eprintln!("{code}");
        std::process::exit(2);
    }
}

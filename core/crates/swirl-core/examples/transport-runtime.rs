//! Isolated integration harness for the additive native transport boundary.
//! Synthetic test settings arrive on bounded stdin; stdout contains only
//! runtime/probe status and fixed errors, never outbound credentials.
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    io::{self, BufRead, Write},
};
use swirl_core::Core;
use swirl_protocol::Transport;
use swirl_subscription::Config;

#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
enum Command {
    Start {
        config: Config,
        #[serde(default)]
        transports: BTreeMap<String, Transport>,
    },
    Configure {
        config: Config,
    },
    ConfigureWithTransports {
        config: Config,
        transports: BTreeMap<String, Transport>,
    },
    SelectNode {
        id: String,
    },
    SelectGroup {
        id: String,
        member: String,
    },
    ProbeStart {
        url: String,
        timeout_ms: Option<u64>,
        expected_status: Option<u16>,
    },
    ProbeStatus,
    ProbeCancel,
    Status,
    Stop,
}

fn dispatch(core: &mut Option<Core>, input: &[u8]) -> Result<Value, &'static str> {
    let command = serde_json::from_slice(input).map_err(|_| "CommandJson")?;
    if let Command::Start { config, transports } = command {
        if core.is_some() {
            return Err("CoreAlreadyStarted");
        }
        *core = Some(Core::start_with_transports(config, transports)?);
        return Ok(json!({"status": core.as_ref().ok_or("CoreMissing")?.snapshot()?}));
    }
    let running = core.as_mut().ok_or("CoreMissing")?;
    match command {
        Command::Configure { config } => running.configure(config)?,
        Command::ConfigureWithTransports { config, transports } => {
            running.configure_with_transports(config, transports)?;
        }
        Command::SelectNode { id } => running.select_node(&id)?,
        Command::SelectGroup { id, member } => running.select_group(&id, &member)?,
        Command::ProbeStart {
            url,
            timeout_ms,
            expected_status,
        } => {
            return Ok(json!({"probe": running.probe_start(url, timeout_ms, expected_status)?}));
        }
        Command::ProbeStatus => return Ok(json!({"probe": running.probe_status()?})),
        Command::ProbeCancel => return Ok(json!({"probe": running.probe_cancel()?})),
        Command::Stop => {
            running.stop();
            *core = None;
            return Ok(json!({}));
        }
        Command::Status => {}
        Command::Start { .. } => unreachable!(),
    }
    Ok(json!({"status": running.snapshot()?}))
}

fn main() {
    let mut core = None;
    let mut input = io::stdin().lock();
    let mut output = io::stdout().lock();
    loop {
        let mut line = Vec::new();
        loop {
            let Ok(buffer) = input.fill_buf() else {
                return;
            };
            if buffer.is_empty() {
                return;
            }
            let count = buffer
                .iter()
                .position(|byte| *byte == b'\n')
                .map_or(buffer.len(), |index| index + 1);
            if line.len() + count > 1024 * 1024 {
                return;
            }
            line.extend_from_slice(&buffer[..count]);
            input.consume(count);
            if line.ends_with(b"\n") {
                break;
            }
        }
        let response = match dispatch(&mut core, &line) {
            Ok(mut value) => {
                value["ok"] = json!(true);
                value
            }
            Err(code) => json!({"ok": false, "error": code}),
        };
        if writeln!(output, "{response}")
            .and_then(|_| output.flush())
            .is_err()
        {
            return;
        }
    }
}

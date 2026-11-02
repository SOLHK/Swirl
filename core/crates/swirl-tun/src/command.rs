//! JSON control plane for the future helper. Commands describe host changes
//! and apply them only to the in-memory store.
use serde_json::{Value, json};

use crate::{
    link::LinkEvent,
    plan,
    recovery::{MemoryStore, NetworkSnapshot},
    service::{Controller, Phase},
};

pub struct Control {
    controller: Controller,
}

impl Control {
    pub fn new() -> Self {
        Self {
            controller: Controller::new(MemoryStore::new(NetworkSnapshot::system()), "Ethernet"),
        }
    }

    pub fn controller(&self) -> &Controller {
        &self.controller
    }
}

impl Default for Control {
    fn default() -> Self {
        Self::new()
    }
}

pub fn command(control: &mut Control, input: &[u8]) -> Vec<u8> {
    let value = match invoke(control, input) {
        Ok(value) => value,
        Err(code) => json!({"ok": false, "error": code}),
    };
    value.to_string().into_bytes()
}

fn invoke(control: &mut Control, input: &[u8]) -> Result<Value, &'static str> {
    if input.is_empty() || input.len() > 64 * 1024 {
        return Err("TunCommandSize");
    }
    let parsed: Value = serde_json::from_slice(input).map_err(|_| "TunCommand")?;
    let op = parsed
        .get("op")
        .and_then(Value::as_str)
        .ok_or("TunCommand")?;
    match op {
        "status" => Ok(status(control)),
        "start" => {
            let owner = text(&parsed, "owner")?;
            let physical = text(&parsed, "physical")?;
            let proxies = addresses(parsed.get("proxies"))?;
            control.controller.start(owner, physical, &proxies)?;
            Ok(status(control))
        }
        "stop" => {
            control.controller.stop()?;
            Ok(status(control))
        }
        "link" => {
            let event = match text(&parsed, "event")? {
                "down" => LinkEvent::Down,
                "up" => LinkEvent::Up,
                "sleep" => LinkEvent::Sleep,
                "resume" => LinkEvent::Resume,
                _ => return Err("TunLinkEvent"),
            };
            control.controller.on_link(event)?;
            Ok(status(control))
        }
        "execute" => {
            plan::execute(control.controller.commands(), false)?;
            Ok(status(control))
        }
        "conflicts" => {
            let names = parsed
                .get("adapters")
                .and_then(Value::as_array)
                .ok_or("TunCommand")?
                .iter()
                .map(|value| value.as_str().ok_or("TunCommand"))
                .collect::<Result<Vec<_>, _>>()?;
            Ok(json!({"ok": true, "foreign": plan::foreign_tunnels(&names)}))
        }
        _ => Err("TunCommand"),
    }
}

fn status(control: &Control) -> Value {
    let phase = match control.controller.phase() {
        Phase::Idle => "idle",
        Phase::Running => "running",
        Phase::Stopped => "stopped",
    };
    json!({
        "ok": true,
        "phase": phase,
        "packets": control.controller.packets_allowed(),
        "journal": control.controller.journal_phase().map(|phase| format!("{phase:?}")),
        "commands": control.controller.commands().len(),
        "owner": control.controller.store().owner,
        "journal_owner": control.controller.journal_owner(),
        "saved_generation": control.controller.saved_generation(),
        "interface": control.controller.link_interface(),
        "adapters": control.controller.store().adapters,
    })
}

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str, &'static str> {
    value
        .get(key)
        .and_then(Value::as_str)
        .filter(|text| !text.is_empty())
        .ok_or("TunCommand")
}

fn addresses(value: Option<&Value>) -> Result<Vec<std::net::IpAddr>, &'static str> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    value
        .as_array()
        .ok_or("TunCommand")?
        .iter()
        .map(|item| {
            item.as_str()
                .ok_or("TunCommand")?
                .parse()
                .map_err(|_| "TunCommand")
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn start_stop_and_execute_never_change_the_host() {
        let mut control = Control::new();
        let started = command(
            &mut control,
            br#"{"op":"start","owner":"tun-owner-1","physical":"Ethernet","proxies":["203.0.113.10"]}"#,
        );
        let started: Value = serde_json::from_slice(&started).unwrap();
        assert_eq!(started["phase"], "running");
        assert_eq!(started["packets"], true);
        assert!(started["commands"].as_u64().unwrap() >= 4);
        assert!(
            control
                .controller
                .store()
                .adapters
                .iter()
                .any(|name| name == "Swirl")
        );
        let refused = command(&mut control, br#"{"op":"execute"}"#);
        let refused: Value = serde_json::from_slice(&refused).unwrap();
        assert_eq!(refused["error"], "HostMutationNotAuthorized");
        let paused = command(&mut control, br#"{"op":"link","event":"sleep"}"#);
        let paused: Value = serde_json::from_slice(&paused).unwrap();
        assert_eq!(paused["packets"], false);
        let _ = command(&mut control, br#"{"op":"stop"}"#);
        assert_eq!(control.controller.store().owner, "system");
        assert!(
            !control
                .controller
                .store()
                .adapters
                .iter()
                .any(|name| name == "Swirl")
        );
        let conflicts = command(
            &mut control,
            br#"{"op":"conflicts","adapters":["Swirl","Ethernet","WireGuard Tunnel"]}"#,
        );
        let conflicts: Value = serde_json::from_slice(&conflicts).unwrap();
        assert_eq!(conflicts["foreign"], json!(["WireGuard Tunnel"]));
    }
}

//! Schema 1 native TUN lifecycle. The ordinary DLL controller never elevates
//! the GUI; only the explicitly launched helper may execute OS mutations.
use super::Controller;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::PathBuf;
use swirl_core::v2::{decimal, identity_uuid};

type Result<T> = std::result::Result<T, &'static str>;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NativeTunConfig {
    pub driver_path: PathBuf,
    pub adapter_guid: String,
    pub adapter_name: String,
    #[serde(default = "default_mtu")]
    pub mtu: u16,
    #[serde(default = "default_tcp")]
    pub max_tcp_flows: u16,
    #[serde(default = "default_udp")]
    pub max_udp_flows: u16,
}
fn default_mtu() -> u16 {
    1500
}
fn default_tcp() -> u16 {
    256
}
fn default_udp() -> u16 {
    128
}

impl NativeTunConfig {
    pub fn validate(&self) -> Result<()> {
        identity_uuid(&self.adapter_guid)?;
        if self.adapter_guid == "00000000-0000-0000-0000-000000000000"
            || self.adapter_guid != self.adapter_guid.to_ascii_lowercase()
            || self.adapter_name.is_empty()
            || self.adapter_name.contains('\0')
            || self.adapter_name.encode_utf16().count() > 127
            || !(1280..=9000).contains(&self.mtu)
            || !(1..=1024).contains(&self.max_tcp_flows)
            || !(1..=512).contains(&self.max_udp_flows)
            || self.driver_path.as_os_str().is_empty()
        {
            return Err("TunConfiguration");
        }
        #[cfg(windows)]
        if !self.driver_path.is_absolute() {
            return Err("TunDriverAbsolutePathRequired");
        }
        self.stack_config().validate().map_err(|_| "TunLimits")
    }

    pub fn stack_config(&self) -> swirl_tun::TunConfig {
        swirl_tun::TunConfig {
            mtu: usize::from(self.mtu),
            max_tcp_flows: usize::from(self.max_tcp_flows),
            max_udp_endpoints: usize::from(self.max_udp_flows),
            ..Default::default()
        }
    }

    #[cfg(windows)]
    pub(crate) fn guid(&self) -> Result<u128> {
        self.validate()?;
        u128::from_str_radix(&self.adapter_guid.replace('-', ""), 16)
            .map_err(|_| "TunConfiguration")
    }
}

struct Request {
    native_tun_schema: u32,
    request_id: String,
    command: Command,
}

fn parse_request(input: &[u8]) -> Result<Request> {
    let mut fields: serde_json::Map<String, Value> =
        serde_json::from_slice(input).map_err(|_| "TunCommandInvalid")?;
    let schema = fields
        .remove("native_tun_schema")
        .and_then(|value| value.as_u64())
        .and_then(|value| u32::try_from(value).ok())
        .ok_or("TunCommandInvalid")?;
    let id = match fields.remove("request_id") {
        Some(Value::String(id)) => id,
        _ => return Err("TunCommandInvalid"),
    };
    // Strip exactly the two envelope fields, then use the tagged command's
    // strict decoder. serde flatten + deny_unknown_fields is not supported.
    let command = serde_json::from_value(Value::Object(fields)).map_err(|_| "TunCommandInvalid")?;
    Ok(Request {
        native_tun_schema: schema,
        request_id: id,
        command,
    })
}

#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
enum Command {
    #[serde(rename = "native_tun_validate")]
    Validate { config: NativeTunConfig },
    #[serde(rename = "native_tun_start")]
    Start {
        handle: String,
        engine_epoch: String,
        config: NativeTunConfig,
    },
    #[serde(rename = "native_tun_status")]
    Status {
        handle: String,
        engine_epoch: String,
    },
    #[serde(rename = "native_tun_stop")]
    Stop {
        handle: String,
        engine_epoch: String,
    },
    #[serde(rename = "native_tun_recover")]
    Recover {},
}

pub(crate) fn dispatch(controller: &mut Controller, input: &[u8]) -> Value {
    let request = match parse_request(input) {
        Ok(request) => request,
        Err(_) => return json!({"ok":false,"native_tun_schema":1,"error":"TunCommandInvalid"}),
    };
    let id = request.request_id.clone();
    let result = if request.native_tun_schema != 1 {
        Err("TunUnsupportedSchema")
    } else if identity_uuid(&id).is_err() {
        Err("InvalidRequestId")
    } else {
        execute(controller, request.command)
    };
    match result {
        Ok(mut value) => {
            value["ok"] = json!(true);
            value["request_id"] = json!(id);
            value["native_tun_schema"] = json!(1);
            value
        }
        Err(error) => json!({"ok":false,"native_tun_schema":1,"request_id":id,"error":error}),
    }
}

fn identity(controller: &Controller, handle: &str, epoch: &str) -> Result<u64> {
    let handle = decimal(handle)?;
    let core = controller.cores_v2.get(&handle).ok_or("UnknownHandle")?;
    if core.configuration()?["engine_epoch"].as_str() != Some(epoch) {
        return Err("EngineEpochMismatch");
    }
    Ok(handle)
}

fn execute(controller: &mut Controller, command: Command) -> Result<Value> {
    match command {
        Command::Validate { config } => {
            config.validate()?;
            Ok(
                json!({"validated":true,"capabilities":capabilities(),"network_plan":{
                    "ipv4_address":"198.18.0.1/30","ipv6_address":"fd53:7769:726c::1/126",
                    "dns":["198.18.0.2","fd53:7769:726c::2"],"mtu":config.mtu,
                    "physical_dns_modified":false,"physical_routes_removed":false,
                    "requires_encrypted_dns":true,"requires_privileged_helper":true,
                    "socket_payload_budget_bytes": u64::from(config.max_tcp_flows)*65536*4+u64::from(config.max_udp_flows)*65536*2,
                    "additional_memory":"packet/datagram queues, fragment buffers, metadata, Wintun rings and native outbounds"
                }}),
            )
        }
        Command::Start {
            handle,
            engine_epoch,
            config,
        } => {
            if !controller.native_helper {
                return Err("TunHelperRequired");
            }
            let handle = identity(controller, &handle, &engine_epoch)?;
            config.validate()?;
            #[cfg(windows)]
            {
                if !controller.native_sessions.is_empty() {
                    return Err("TunAlreadyOwned");
                }
                let dispatcher = controller
                    .cores_v2
                    .get(&handle)
                    .ok_or("UnknownHandle")?
                    .flow_dispatcher()?;
                let session = super::native_windows::NativeSession::start(dispatcher, config)?;
                let status = session.status();
                controller.native_sessions.insert(handle, session);
                Ok(status)
            }
            #[cfg(not(windows))]
            {
                let _ = (handle, config);
                Err("TunWindowsRequired")
            }
        }
        Command::Status {
            handle,
            engine_epoch,
        } => {
            let handle = identity(controller, &handle, &engine_epoch)?;
            #[cfg(windows)]
            if let Some(session) = controller.native_sessions.get(&handle) {
                return Ok(session.status());
            }
            let _ = handle;
            Ok(json!({"state":"stopped","desired_enabled":false,"capabilities":capabilities()}))
        }
        Command::Stop {
            handle,
            engine_epoch,
        } => {
            if !controller.native_helper {
                return Err("TunHelperRequired");
            }
            let handle = identity(controller, &handle, &engine_epoch)?;
            stop_for_core(controller, handle)?;
            Ok(json!({"state":"stopped","desired_enabled":false}))
        }
        Command::Recover {} => {
            if !controller.native_helper {
                return Err("TunHelperRequired");
            }
            #[cfg(windows)]
            {
                super::native_windows::recover_stale()
            }
            #[cfg(not(windows))]
            {
                Err("TunWindowsRequired")
            }
        }
    }
}

pub(crate) fn stop_for_core(controller: &mut Controller, handle: u64) -> Result<()> {
    #[cfg(windows)]
    if let Some(session) = controller.native_sessions.get_mut(&handle) {
        session.stop()?;
        controller.native_sessions.remove(&handle);
    }
    let _ = (controller, handle);
    Ok(())
}

pub fn capabilities() -> Value {
    json!({
        "schema":1,"packet_backend":true,"windows_driver_compiled":cfg!(windows),
        "controller_requires_helper":true,"driver_version":"0.14.1",
        "tcp":true,"udp":true,"ipv4":true,"ipv6":true,"fake_ip":true,
        "encrypted_dns_required":true,"real_windows_11_acceptance":false,
        "system_kill_switch":false,"capture_continuous_during_network_restart":false,
        "icmp_relay":false,"arbitrary_ipv6_extensions":false,"automatic_gui_elevation":false,
        "gateway_control":super::native_gateway_control::capabilities()
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request(op: &str) -> Value {
        json!({"native_tun_schema":1,"request_id":"60000000-0000-4000-8000-000000000001","op":op})
    }
    fn config() -> Value {
        json!({"driver_path":"C:\\Swirl\\fixture-driver.dll","adapter_guid":"70000000-0000-4000-8000-000000000001","adapter_name":"Swirl Native TUN"})
    }
    #[test]
    fn validation_is_offline_and_gui_cannot_start_or_recover_network() {
        let mut controller = Controller::default();
        let mut validation = request("native_tun_validate");
        validation["config"] = config();
        let value = controller.dispatch(&serde_json::to_vec(&validation).unwrap());
        assert_eq!(value["ok"], true, "{value}");
        assert_eq!(value["network_plan"]["requires_privileged_helper"], true);
        let mut start = request("native_tun_start");
        start["config"] = config();
        start["handle"] = json!("1");
        start["engine_epoch"] = json!("80000000-0000-4000-8000-000000000001");
        assert_eq!(
            controller.dispatch(&serde_json::to_vec(&start).unwrap())["error"],
            "TunHelperRequired"
        );
        assert_eq!(
            controller.dispatch(&serde_json::to_vec(&request("native_tun_recover")).unwrap())["error"],
            "TunHelperRequired"
        );
        validation["config"]["mtu"] = json!(65535);
        assert_eq!(
            controller.dispatch(&serde_json::to_vec(&validation).unwrap())["error"],
            "TunConfiguration"
        );
    }
    #[test]
    fn unsupported_schema_and_unknown_options_never_fall_back() {
        let mut controller = Controller::default();
        let mut value = request("native_tun_recover");
        value["native_tun_schema"] = json!(2);
        assert_eq!(
            controller.dispatch(&serde_json::to_vec(&value).unwrap())["error"],
            "TunUnsupportedSchema"
        );
        value["native_tun_schema"] = json!(1);
        value["shell_command"] = json!("anything");
        assert_eq!(
            controller.dispatch(&serde_json::to_vec(&value).unwrap())["error"],
            "TunCommandInvalid"
        );
    }
}

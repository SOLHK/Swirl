//! Versioned, helper-only gateway control. Preparation installs isolation and
//! the existing TUN data plane, but never enables LAN forwarding by itself.
use super::{Controller, native_tun_control::NativeTunConfig};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use swirl_core::v2::{decimal, identity_uuid};
use swirl_platform::gateway_policy::GatewayRequest;

type Result<T> = std::result::Result<T, &'static str>;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NativeGatewayConfig {
    pub tun: NativeTunConfig,
    pub lan: GatewayRequest,
    #[serde(default = "default_tcp")]
    pub max_tcp_per_client: usize,
    #[serde(default = "default_udp")]
    pub max_udp_per_client: usize,
    #[serde(default = "default_dns")]
    pub max_dns_per_client: usize,
}
fn default_tcp() -> usize {
    64
}
fn default_udp() -> usize {
    32
}
fn default_dns() -> usize {
    8
}

impl NativeGatewayConfig {
    pub fn validate(&self) -> Result<()> {
        self.tun.validate()?;
        self.lan.validate().map_err(|_| "GatewayConfiguration")?;
        if self.lan.lan.guid == self.tun.adapter_guid
            || !(1..=usize::from(self.tun.max_tcp_flows)).contains(&self.max_tcp_per_client)
            || !(1..=usize::from(self.tun.max_udp_flows)).contains(&self.max_udp_per_client)
            || !(1..=16).contains(&self.max_dns_per_client)
        {
            return Err("GatewayLimitsOrInterfaceIdentity");
        }
        Ok(())
    }
}

/// The helper verifies this process's start time, sibling Swirl.exe image and
/// live UDP/67 ownership. It is not a caller-supplied "DHCP is running" boolean.
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DhcpAttachment {
    pub owner_pid: u32,
    pub owner_creation: String,
    pub target_helper_pid: u32,
    pub protocol_info_base64: String,
}
impl DhcpAttachment {
    pub fn validate(&self) -> Result<()> {
        if self.owner_pid == 0
            || decimal(&self.owner_creation)? == 0
            || self.target_helper_pid == 0
            || self.protocol_info_base64.is_empty()
            || self.protocol_info_base64.len() > 1024
        {
            return Err("GatewayDhcpAttachment");
        }
        Ok(())
    }
}

#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
enum Command {
    #[serde(rename = "gateway_validate")]
    Validate { config: NativeGatewayConfig },
    #[serde(rename = "gateway_prepare")]
    Prepare {
        handle: String,
        engine_epoch: String,
        config: NativeGatewayConfig,
    },
    #[serde(rename = "gateway_activate")]
    Activate {
        handle: String,
        engine_epoch: String,
        preparation_id: String,
        #[serde(default)]
        dhcp: Option<DhcpAttachment>,
    },
    #[serde(rename = "gateway_status")]
    Status {
        handle: String,
        engine_epoch: String,
    },
    #[serde(rename = "gateway_stop")]
    Stop {
        handle: String,
        engine_epoch: String,
    },
    #[serde(rename = "gateway_recover")]
    Recover {},
}

pub(crate) fn dispatch(controller: &mut Controller, input: &[u8]) -> Value {
    let parsed = (|| -> Result<(u64, String, Command)> {
        let mut fields: serde_json::Map<String, Value> =
            serde_json::from_slice(input).map_err(|_| "GatewayCommandInvalid")?;
        let schema = fields
            .remove("native_gateway_schema")
            .and_then(|value| value.as_u64())
            .ok_or("GatewayCommandInvalid")?;
        let request = match fields.remove("request_id") {
            Some(Value::String(value)) => value,
            _ => return Err("GatewayCommandInvalid"),
        };
        let command =
            serde_json::from_value(Value::Object(fields)).map_err(|_| "GatewayCommandInvalid")?;
        Ok((schema, request, command))
    })();
    let (schema, request, command) = match parsed {
        Ok(value) => value,
        Err(error) => return json!({"ok":false,"native_gateway_schema":1,"error":error}),
    };
    let valid_request = identity_uuid(&request).is_ok();
    let result = if schema != 1 {
        Err("GatewayUnsupportedSchema")
    } else if !valid_request {
        Err("InvalidRequestId")
    } else {
        execute(controller, command)
    };
    let request = if valid_request {
        request
    } else {
        String::new()
    };
    match result {
        Ok(mut value) => {
            value["ok"] = json!(true);
            value["request_id"] = json!(request);
            value["native_gateway_schema"] = json!(1);
            value
        }
        Err(error) => {
            json!({"ok":false,"native_gateway_schema":1,"request_id":request,"error":error})
        }
    }
}

fn identity(controller: &Controller, handle: &str, epoch: &str) -> Result<u64> {
    let handle = decimal(handle)?;
    let core = controller.cores_v2.get(&handle).ok_or("UnknownV2Handle")?;
    if core.epoch() != decimal(epoch)? {
        return Err("EngineEpochMismatch");
    }
    Ok(handle)
}

fn helper(controller: &Controller) -> Result<()> {
    if !controller.native_helper {
        return Err("GatewayHelperRequired");
    }
    Ok(())
}

fn execute(controller: &mut Controller, command: Command) -> Result<Value> {
    match command {
        Command::Validate { config } => {
            config.validate()?;
            Ok(json!({"validated":true,"network_preflight_required":true,
                "dns_ipv4":"198.18.0.2","requires_static_dedicated_lan":true,
                "capabilities":capabilities()}))
        }
        Command::Prepare {
            handle,
            engine_epoch,
            config,
        } => {
            helper(controller)?;
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
                    .ok_or("UnknownV2Handle")?
                    .flow_dispatcher()?;
                let session =
                    super::native_windows::NativeSession::prepare_gateway(dispatcher, config)?;
                let status = session.status();
                controller.native_sessions.insert(handle, session);
                Ok(status)
            }
            #[cfg(not(windows))]
            {
                let _ = (handle, config);
                Err("GatewayWindowsRequired")
            }
        }
        Command::Activate {
            handle,
            engine_epoch,
            preparation_id,
            dhcp,
        } => {
            helper(controller)?;
            let handle = identity(controller, &handle, &engine_epoch)?;
            if preparation_id.len() != 32 || !preparation_id.bytes().all(|b| b.is_ascii_hexdigit())
            {
                return Err("GatewayPreparationIdentity");
            }
            if let Some(attachment) = &dhcp {
                attachment.validate()?;
            }
            #[cfg(windows)]
            {
                let session = controller
                    .native_sessions
                    .get_mut(&handle)
                    .ok_or("GatewayNotPrepared")?;
                session.activate_gateway(&preparation_id, dhcp)?;
                Ok(session.status())
            }
            #[cfg(not(windows))]
            {
                let _ = (handle, preparation_id, dhcp);
                Err("GatewayWindowsRequired")
            }
        }
        Command::Status {
            handle,
            engine_epoch,
        } => {
            let handle = identity(controller, &handle, &engine_epoch)?;
            #[cfg(windows)]
            if let Some(session) = controller.native_sessions.get(&handle) {
                if !session.is_gateway() {
                    return Err("GatewayNotPrepared");
                }
                return Ok(session.status());
            }
            let _ = handle;
            Ok(json!({"state":"stopped","desired_enabled":false,"capabilities":capabilities()}))
        }
        Command::Stop {
            handle,
            engine_epoch,
        } => {
            helper(controller)?;
            let handle = identity(controller, &handle, &engine_epoch)?;
            #[cfg(windows)]
            if let Some(session) = controller.native_sessions.get(&handle)
                && !session.is_gateway()
            {
                return Err("GatewayNotPrepared");
            }
            super::native_tun_control::stop_for_core(controller, handle)?;
            Ok(json!({"state":"stopped","desired_enabled":false}))
        }
        Command::Recover {} => {
            helper(controller)?;
            #[cfg(windows)]
            {
                super::native_windows::recover_stale()
            }
            #[cfg(not(windows))]
            {
                Err("GatewayWindowsRequired")
            }
        }
    }
}

pub fn capabilities() -> Value {
    json!({"schema":1,"backend_compiled":cfg!(windows),"controller_requires_helper":true,
        "prepare_activate":true,"ipv4_only":true,"ipv6_forwarding":false,
        "dhcp_attachment_requires_socket_owner":true,"dhcp_socket_attestation":true,
        "automatic_gui_elevation":false,
        "gui_activation_available":false,"automatic_boot_recovery":false,
        "real_windows_11_acceptance":false,"tun_dependency":"930c3f5fc2cbcfb99de4769c44f1682f4fc2e01d"})
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request(op: &str) -> Value {
        json!({"native_gateway_schema":1,"op":op,"request_id":"60000000-0000-4000-8000-000000000001"})
    }
    fn config() -> Value {
        json!({"tun":{"driver_path":"C:\\Swirl\\fixture-driver.dll","adapter_guid":"70000000-0000-4000-8000-000000000001","adapter_name":"Swirl Native TUN"},
            "lan":{"lan":{"index":11,"guid":"70000000-0000-4000-8000-000000000002"},
                "subnet":"192.168.77.0/24","gateway":"192.168.77.1",
                "allowed_sources":["192.168.77.0/24"],"dedicated_lan_confirmed":true,"dhcp":false}})
    }
    #[test]
    fn pure_validation_and_gui_mutation_rejection() {
        let mut controller = Controller::default();
        let mut value = request("gateway_validate");
        value["config"] = config();
        let response = controller.dispatch(&serde_json::to_vec(&value).unwrap());
        assert_eq!(response["ok"], true, "{response}");
        assert_eq!(response["network_preflight_required"], true);
        assert!(controller.cores_v2.is_empty());
        value["op"] = json!("gateway_prepare");
        value["handle"] = json!("1");
        value["engine_epoch"] = json!("1");
        assert_eq!(
            controller.dispatch(&serde_json::to_vec(&value).unwrap())["error"],
            "GatewayHelperRequired"
        );
        assert_eq!(
            controller.dispatch(&serde_json::to_vec(&request("gateway_recover")).unwrap())["error"],
            "GatewayHelperRequired"
        );
    }
    #[test]
    fn unknown_fields_unsafe_lan_and_request_identity_fail_closed() {
        let mut controller = Controller::default();
        let mut value = request("gateway_validate");
        value["config"] = config();
        value["config"]["lan"]["dedicated_lan_confirmed"] = json!(false);
        assert_eq!(
            controller.dispatch(&serde_json::to_vec(&value).unwrap())["ok"],
            false
        );
        value["config"] = config();
        value["request_id"] = json!("PRIVATE_REQUEST_SECRET");
        let response = controller.dispatch(&serde_json::to_vec(&value).unwrap());
        assert_eq!(response["ok"], false);
        assert!(!response.to_string().contains("PRIVATE_REQUEST_SECRET"));
        value["op"] = json!("gateway_validate");
        value["shell_command"] = json!("PRIVATE_REQUEST_SECRET");
        assert_eq!(
            controller.dispatch(&serde_json::to_vec(&value).unwrap())["error"],
            "GatewayCommandInvalid"
        );
    }
    #[test]
    fn no_dhcp_ready_boolean_or_bad_creation_identity_is_accepted() {
        assert!(serde_json::from_value::<DhcpAttachment>(json!({"owner_pid":1,"owner_creation":"01","target_helper_pid":2,"protocol_info_base64":"AA=="})).unwrap().validate().is_err());
        assert!(serde_json::from_value::<DhcpAttachment>(json!({"owner_pid":1,"owner_creation":"1","target_helper_pid":2,"protocol_info_base64":"AA==","ready":true})).is_err());
        assert!(serde_json::from_value::<DhcpAttachment>(json!({"owner_pid":1,"owner_creation":"1","target_helper_pid":2,"protocol_info_base64":"A".repeat(1025)})).unwrap().validate().is_err());
        assert_eq!(capabilities()["gui_activation_available"], false);
        assert_eq!(capabilities()["real_windows_11_acceptance"], false);
    }
}

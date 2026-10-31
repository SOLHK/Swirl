//! Control schema 2 is explicitly dispatched; malformed V2 never tries V1.
use super::Controller;
use serde::Deserialize;
use serde_json::{Value, json};
use swirl_core::lan::LanConfig;
use swirl_core::v2::{Core, DurableReceipt, RuntimeConfig, decimal, identity_uuid};
#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
enum Command {
    ValidateConfigurationV2 {
        control_schema: u32,
        request_id: String,
        candidate: RuntimeConfig,
    },
    StartV2 {
        control_schema: u32,
        request_id: String,
        store_id: String,
        saved_revision: String,
        candidate: RuntimeConfig,
        #[serde(default)]
        plan_digest: Option<String>,
    },
    PrepareConfigurationV2 {
        control_schema: u32,
        request_id: String,
        handle: String,
        engine_epoch: String,
        store_id: String,
        base_saved_revision: String,
        candidate_revision: String,
        expected_generation: String,
        base_applied_revision: String,
        candidate: RuntimeConfig,
        #[serde(default)]
        revoked_node_ids: Vec<String>,
    },
    ActivateConfigurationV2 {
        control_schema: u32,
        request_id: String,
        handle: String,
        engine_epoch: String,
        prepared_token: String,
        plan_digest: String,
        expected_generation: String,
        candidate_revision: String,
    },
    FinishConfigurationV2 {
        control_schema: u32,
        request_id: String,
        handle: String,
        engine_epoch: String,
        prepared_token: String,
        durable_receipt: DurableReceipt,
    },
    RollbackConfigurationV2 {
        control_schema: u32,
        request_id: String,
        handle: String,
        engine_epoch: String,
        prepared_token: String,
        expected_generation: String,
        old_committed: DurableReceipt,
    },
    ConfigurationStatusV2 {
        control_schema: u32,
        request_id: String,
        handle: String,
        engine_epoch: String,
    },
    LanValidate {
        control_schema: u32,
        request_id: String,
        config: LanConfig,
    },
    LanStart {
        control_schema: u32,
        request_id: String,
        handle: String,
        engine_epoch: String,
        config: LanConfig,
    },
    LanStop {
        control_schema: u32,
        request_id: String,
        handle: String,
        engine_epoch: String,
    },
    LanStatus {
        control_schema: u32,
        request_id: String,
        handle: String,
        engine_epoch: String,
    },
}
impl Command {
    fn online_handle(&self) -> Option<&str> {
        match self {
            Self::PrepareConfigurationV2 { handle, .. }
            | Self::ActivateConfigurationV2 { handle, .. }
            | Self::FinishConfigurationV2 { handle, .. }
            | Self::RollbackConfigurationV2 { handle, .. }
            | Self::ConfigurationStatusV2 { handle, .. }
            | Self::LanStart { handle, .. }
            | Self::LanStop { handle, .. }
            | Self::LanStatus { handle, .. } => Some(handle),
            _ => None,
        }
    }
    fn conflicts(&self) -> Vec<swirl_subscription::v2::Conflict> {
        match self {
            Self::ValidateConfigurationV2 { candidate, .. }
            | Self::PrepareConfigurationV2 { candidate, .. } => {
                let mut policy = candidate.policy.clone();
                if policy.normalize().is_ok() {
                    policy.conflicts()
                } else {
                    Vec::new()
                }
            }
            _ => Vec::new(),
        }
    }
    fn common(&self) -> (u32, &str, &'static str) {
        match self {
            Self::ValidateConfigurationV2 {
                control_schema,
                request_id,
                ..
            } => (*control_schema, request_id, "validate"),
            Self::StartV2 {
                control_schema,
                request_id,
                ..
            } => (*control_schema, request_id, "start"),
            Self::PrepareConfigurationV2 {
                control_schema,
                request_id,
                ..
            } => (*control_schema, request_id, "prepare"),
            Self::ActivateConfigurationV2 {
                control_schema,
                request_id,
                ..
            } => (*control_schema, request_id, "activate"),
            Self::FinishConfigurationV2 {
                control_schema,
                request_id,
                ..
            } => (*control_schema, request_id, "finish"),
            Self::RollbackConfigurationV2 {
                control_schema,
                request_id,
                ..
            } => (*control_schema, request_id, "rollback"),
            Self::ConfigurationStatusV2 {
                control_schema,
                request_id,
                ..
            } => (*control_schema, request_id, "status"),
            Self::LanValidate {
                control_schema,
                request_id,
                ..
            } => (*control_schema, request_id, "lan_validate"),
            Self::LanStart {
                control_schema,
                request_id,
                ..
            } => (*control_schema, request_id, "lan_start"),
            Self::LanStop {
                control_schema,
                request_id,
                ..
            } => (*control_schema, request_id, "lan_stop"),
            Self::LanStatus {
                control_schema,
                request_id,
                ..
            } => (*control_schema, request_id, "lan_status"),
        }
    }
    fn execute(self, controller: &mut Controller) -> Result<Value, &'static str> {
        let (schema, request, _) = self.common();
        if schema != 2 {
            return Err("UnsupportedControlSchema");
        };
        identity_uuid(request)?;
        match self {
            Self::ValidateConfigurationV2 {
                request_id,
                candidate,
                ..
            } => {
                let prepared = candidate.prepare()?;
                Ok(
                    json!({"ok":true,"request_id":request_id,"plan_digest":prepared.digest,"validation":{"conflicts":prepared.conflicts},"capabilities":capabilities()}),
                )
            }
            Self::StartV2 {
                request_id,
                store_id,
                saved_revision,
                candidate,
                plan_digest,
                ..
            } => {
                if controller.cores.len() + controller.cores_v2.len() >= 4 {
                    return Err("CoreLimit");
                }
                if let Some(expected) = plan_digest
                    && candidate.clone().prepare()?.digest != expected
                {
                    return Err("ReceiptMismatch");
                }
                let core = Core::start(
                    candidate,
                    store_id,
                    decimal(&saved_revision)?,
                    request_id.clone(),
                )?;
                controller.next = controller.next.checked_add(1).ok_or("HandleLimit")?;
                let handle = controller.next;
                let mut response = core.configuration()?;
                response["request_id"] = json!(request_id);
                response["handle"] = json!(handle.to_string());
                response["status"] = core.snapshot()?;
                controller.cores_v2.insert(handle, core);
                Ok(response)
            }
            Self::PrepareConfigurationV2 {
                request_id,
                handle,
                engine_epoch,
                store_id,
                base_saved_revision,
                candidate_revision,
                expected_generation,
                base_applied_revision,
                candidate,
                revoked_node_ids,
                ..
            } => checked_core(controller, &handle, &engine_epoch)?.prepare(
                request_id,
                &store_id,
                decimal(&base_saved_revision)?,
                decimal(&candidate_revision)?,
                decimal(&expected_generation)?,
                decimal(&base_applied_revision)?,
                candidate,
                revoked_node_ids,
            ),
            Self::ActivateConfigurationV2 {
                request_id,
                handle,
                engine_epoch,
                prepared_token,
                plan_digest,
                expected_generation,
                candidate_revision,
                ..
            } => checked_core(controller, &handle, &engine_epoch)?.activate(
                &request_id,
                &prepared_token,
                &plan_digest,
                decimal(&expected_generation)?,
                decimal(&candidate_revision)?,
            ),
            Self::FinishConfigurationV2 {
                request_id,
                handle,
                engine_epoch,
                prepared_token,
                durable_receipt,
                ..
            } => checked_core(controller, &handle, &engine_epoch)?.finish(
                &request_id,
                &prepared_token,
                durable_receipt,
            ),
            Self::RollbackConfigurationV2 {
                request_id,
                handle,
                engine_epoch,
                prepared_token,
                expected_generation,
                old_committed,
                ..
            } => {
                let core = checked_core(controller, &handle, &engine_epoch)?;
                if core.store_id() != old_committed.store_id {
                    return Err("StoreIdentityMismatch");
                };
                core.rollback(
                    &request_id,
                    &prepared_token,
                    decimal(&expected_generation)?,
                    decimal(&old_committed.saved_revision)?,
                    &old_committed.plan_digest,
                )
            }
            Self::ConfigurationStatusV2 {
                request_id,
                handle,
                engine_epoch,
                ..
            } => checked_core(controller, &handle, &engine_epoch)?.status(&request_id),
            Self::LanValidate {
                request_id, config, ..
            } => {
                config.validate()?;
                // Syntax and security bounds only. Actual interface ownership,
                // firewall admission and socket availability are checked at start.
                Ok(json!({"ok":true,"request_id":request_id,"lan_control_schema":1,"validation":{"valid":true,"network_preflight_required":true}}))
            }
            Self::LanStart {
                request_id,
                handle,
                engine_epoch,
                config,
                ..
            } => {
                let core = checked_core_mut(controller, &handle, &engine_epoch)?;
                let status = core.lan_start(config)?;
                Ok(json!({"ok":true,"request_id":request_id,"engine_epoch":core.epoch().to_string(),"lan":status}))
            }
            Self::LanStop {
                request_id,
                handle,
                engine_epoch,
                ..
            } => {
                let core = checked_core_mut(controller, &handle, &engine_epoch)?;
                let status = core.lan_stop()?;
                Ok(json!({"ok":true,"request_id":request_id,"engine_epoch":core.epoch().to_string(),"lan":status}))
            }
            Self::LanStatus {
                request_id,
                handle,
                engine_epoch,
                ..
            } => {
                let core = checked_core(controller, &handle, &engine_epoch)?;
                let status = core.lan_status()?;
                Ok(json!({"ok":true,"request_id":request_id,"engine_epoch":core.epoch().to_string(),"lan":status}))
            }
        }
    }
}
fn checked_core_mut<'a>(
    controller: &'a mut Controller,
    handle: &str,
    epoch: &str,
) -> Result<&'a mut Core, &'static str> {
    let core = controller
        .cores_v2
        .get_mut(&decimal(handle)?)
        .ok_or("UnknownV2Handle")?;
    if core.epoch() != decimal(epoch)? {
        return Err("EngineEpochMismatch");
    }
    Ok(core)
}
fn checked_core<'a>(
    controller: &'a Controller,
    handle: &str,
    epoch: &str,
) -> Result<&'a Core, &'static str> {
    let core = controller
        .cores_v2
        .get(&decimal(handle)?)
        .ok_or("UnknownV2Handle")?;
    if core.epoch() != decimal(epoch)? {
        return Err("EngineEpochMismatch");
    };
    Ok(core)
}
pub(super) fn dispatch(controller: &mut Controller, input: &[u8]) -> Value {
    let command: Command = match serde_json::from_slice(input) {
        Ok(command) => command,
        Err(_) => {
            return json!({"ok":false,"error":"CommandInvalidOrUnsupported","code":"CommandInvalidOrUnsupported","phase":"parse"});
        }
    };
    let (_, request, phase) = command.common();
    let request = if identity_uuid(request).is_ok() {
        request.to_owned()
    } else {
        String::new()
    };
    let identity_handle = command.online_handle().and_then(|id| decimal(id).ok());
    let conflicts = command.conflicts();
    match command.execute(controller) {
        Ok(value) => value,
        Err(code) => {
            let identity = identity_handle
                .and_then(|id| controller.cores_v2.get(&id))
                .and_then(|core| core.configuration().ok());
            let mut value = json!({"ok":false,"request_id":request,"error":code,"code":code,"phase":phase,"conflicts":conflicts});
            if let Some(identity) = identity {
                for key in [
                    "engine_epoch",
                    "generation",
                    "store_id",
                    "applied_revision",
                    "applied_mode",
                    "transaction_state",
                ] {
                    value[key] = identity[key].clone();
                }
            }
            value
        }
    }
}
pub(super) fn capabilities() -> Value {
    json!({"required":["config_transactions_v1","stable_policy_ids_v1","routing_tiers_v1"],"optional":{"tun":false,"lan_proxy":true,"lan_proxy_control_schema":1,"lan_proxy_ipv6":false,"lan_proxy_ipv6_listener":false,"lan_proxy_ipv6_targets":true,"gateway":false,"process_matching":false,"application_or_domain_matching":false,"nested_policy_groups_v1":true,"service_affinity_v1":true,"classification_via_default_policy":true}})
}

#[cfg(test)]
#[path = "control_v2_tests.rs"]
mod tests;

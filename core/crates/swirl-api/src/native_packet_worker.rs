//! Experimental inherited-pipe endpoint. Token validation is not broker or
//! service-principal authentication; no product/WFP capability is enabled here.
use crate::{Controller, native_worker_output::BoundedOutput};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    io::{self, BufRead, Write},
    net::SocketAddr,
    sync::{
        Arc,
        atomic::{AtomicBool, AtomicU64, Ordering},
        mpsc,
    },
    thread,
    time::{Duration, Instant},
};
use swirl_core::{
    native_tun::{BridgeControl, BridgeStats, PacketBridge},
    native_tun_ipc::{PacketReader, PacketWriter},
    v2::{decimal, identity_uuid},
};
use swirl_dns::tun::{FakeIpStore, TunDns};
use swirl_platform::{
    windows_packet_resources::{
        InheritedPacketHandles, PacketWorkerResources, clone_inherited_packet_resources,
    },
    windows_restricted_worker::{TokenProfile, current_token_profile},
};
use swirl_transport::egress::EgressLease;
use swirl_tun::{TunConfig, TunStats};

const MAX_FRAME: usize = 1024 * 1024;
const OUTPUT_DRAIN: Duration = Duration::from_secs(2);

fn invalid(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, message)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    packet_worker_schema: u32,
    request_id: String,
    epoch: u64,
    command: Command,
}

#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
enum Command {
    Init {
        mtu: usize,
        max_tcp_flows: usize,
        max_udp_flows: usize,
        resources: InheritedPacketHandles,
    },
    Core {
        json: String,
    },
    BridgeStart {
        handle: String,
        engine_epoch: String,
    },
    Status {},
    Stop {},
}

fn request(bytes: &[u8], epoch: Option<u64>) -> io::Result<Request> {
    let request: Request =
        serde_json::from_slice(bytes).map_err(|_| invalid("PacketWorkerCommand"))?;
    if request.packet_worker_schema != 1
        || request.epoch == 0
        || epoch.is_some_and(|epoch| epoch != request.epoch)
    {
        return Err(invalid("PacketWorkerEpoch"));
    }
    identity_uuid(&request.request_id).map_err(invalid)?;
    Ok(request)
}

fn token_gate(profile: &TokenProfile) -> io::Result<()> {
    if profile.elevated
        || !profile.restricted
        || profile.admin_enabled
        || !profile.admin_deny_only
        || profile.integrity_rid != 0x1000
        || profile.unexpected_enabled_privileges != 0
        || profile.enabled_privileges > 1
    {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "PacketWorkerRestrictedTokenRequired",
        ));
    }
    Ok(())
}

// Keep the original JSON string for Controller's strict V2 parser. In
// particular, never deserialize/re-serialize away duplicate object fields.
fn core_command(raw: &str, id: &str, core_count: usize) -> io::Result<()> {
    let value = swirl_subscription::parse_json_value(raw.as_bytes())
        .map_err(|_| invalid("PacketWorkerCoreJson"))?;
    if value["control_schema"] != 2 || value["request_id"].as_str() != Some(id) {
        return Err(invalid("PacketWorkerCoreIdentity"));
    }
    let op = value["op"]
        .as_str()
        .ok_or_else(|| invalid("PacketWorkerCoreOperation"))?;
    if !matches!(
        op,
        "validate_configuration_v2"
            | "start_v2"
            | "prepare_configuration_v2"
            | "activate_configuration_v2"
            | "finish_configuration_v2"
            | "rollback_configuration_v2"
            | "configuration_status_v2"
    ) {
        return Err(invalid("PacketWorkerCoreOperation"));
    }
    if op == "start_v2" && core_count != 0 {
        return Err(invalid("PacketWorkerSingleCore"));
    }
    if let Some(candidate) = value.get("candidate") {
        let listen = candidate["listen"]
            .as_str()
            .and_then(|v| v.parse::<SocketAddr>().ok())
            .ok_or_else(|| invalid("PacketWorkerListen"))?;
        if !listen.ip().is_loopback() || listen.port() != 0 {
            return Err(invalid("PacketWorkerListen"));
        }
    }
    Ok(())
}

fn read_frame(input: &mut impl BufRead) -> io::Result<Option<Vec<u8>>> {
    let mut frame = Vec::new();
    loop {
        let bytes = input.fill_buf()?;
        if bytes.is_empty() {
            return if frame.is_empty() {
                Ok(None)
            } else {
                Err(invalid("PacketWorkerTruncatedCommand"))
            };
        }
        let size = bytes
            .iter()
            .position(|byte| *byte == b'\n')
            .map_or(bytes.len(), |at| at + 1);
        if frame.len() + size > MAX_FRAME {
            return Err(invalid("PacketWorkerCommandSize"));
        }
        frame.extend_from_slice(&bytes[..size]);
        input.consume(size);
        if frame.ends_with(b"\n") {
            return Ok(Some(frame));
        }
    }
}

fn response_bytes(value: &Value) -> io::Result<Vec<u8>> {
    let bytes = serde_json::to_vec(value)?;
    if bytes.len() + 1 > MAX_FRAME {
        return Err(invalid("PacketWorkerResponseSize"));
    }
    Ok(bytes)
}

fn emit(value: &Value) -> io::Result<()> {
    let bytes = response_bytes(value)?;
    let stdout = io::stdout();
    let mut output = stdout.lock();
    output.write_all(&bytes)?;
    output.write_all(b"\n")?;
    output.flush()
}

#[derive(Default)]
struct PacketIo {
    received: AtomicU64,
    transmitted: AtomicU64,
    queue_dropped: AtomicU64,
    input_done: AtomicBool,
    output_done: AtomicBool,
}

struct Bridge {
    control: BridgeControl,
    runtime: tokio::runtime::Handle,
    stats: TunStats,
    bridge_stats: Arc<BridgeStats>,
    io: Arc<PacketIo>,
    errors: mpsc::Receiver<io::Error>,
}

impl Bridge {
    fn start(
        bridge: PacketBridge,
        runtime: tokio::runtime::Handle,
        resources: (std::fs::File, std::fs::File),
        epoch: u64,
        mtu: usize,
    ) -> io::Result<Self> {
        let PacketBridge {
            input,
            mut output,
            stats,
            bridge_stats,
            control,
        } = bridge;
        let mut reader = PacketReader::new(resources.0, epoch, mtu)?;
        let mut writer = PacketWriter::new(resources.1, epoch, mtu)?;
        let io = Arc::new(PacketIo::default());
        let (failed, errors) = mpsc::sync_channel(2);
        let incoming = io.clone();
        let input_failed = failed.clone();
        thread::Builder::new()
            .name("swirl-packet-input".into())
            .spawn(move || {
                let result: io::Result<()> = (|| {
                    while let Some(packet) = reader.read_packet()? {
                        match input.try_send(packet) {
                            Ok(()) => {
                                incoming.received.fetch_add(1, Ordering::Relaxed);
                            }
                            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                                incoming.queue_dropped.fetch_add(1, Ordering::Relaxed);
                            }
                            Err(error) => return Err(error),
                        }
                    }
                    Err(io::Error::new(
                        io::ErrorKind::UnexpectedEof,
                        "PacketWorkerInputClosed",
                    ))
                })();
                incoming.input_done.store(true, Ordering::Release);
                if let Err(error) = result {
                    let _ = input_failed.try_send(error);
                }
            })?;
        let outgoing = io.clone();
        thread::Builder::new()
            .name("swirl-packet-output".into())
            .spawn(move || {
                let result = (|| {
                    while let Some(packet) = output.blocking_recv() {
                        writer.write_packet(&packet)?;
                        outgoing.transmitted.fetch_add(1, Ordering::Relaxed);
                    }
                    Ok::<_, io::Error>(())
                })();
                outgoing.output_done.store(true, Ordering::Release);
                if let Err(error) = result {
                    let _ = failed.try_send(error);
                }
            })?;
        Ok(Self {
            control,
            runtime,
            stats,
            bridge_stats,
            io,
            errors,
        })
    }

    fn status(&self) -> Value {
        let stats = self.stats.snapshot();
        json!({"received_packets":stats.received_packets,"malformed_packets":stats.malformed_packets,
            "active_tcp_flows":stats.active_tcp_flows,"active_udp_endpoints":stats.active_udp_endpoints,
            "rejected_tcp_flows":stats.rejected_tcp_flows,"dropped_udp_datagrams":stats.dropped_udp_datagrams,
            "tcp_failures":self.bridge_stats.tcp_failures.load(Ordering::Relaxed),"udp_failures":self.bridge_stats.udp_failures.load(Ordering::Relaxed),
            "dns_failures":self.bridge_stats.dns_failures.load(Ordering::Relaxed),"udp_dropped":self.bridge_stats.udp_dropped.load(Ordering::Relaxed),
            "packet_input_accepted":self.io.received.load(Ordering::Relaxed),"packet_output_written":self.io.transmitted.load(Ordering::Relaxed),
            "packet_queue_dropped":self.io.queue_dropped.load(Ordering::Relaxed),
            "packet_input_thread_completed":self.io.input_done.load(Ordering::Acquire),"packet_output_thread_completed":self.io.output_done.load(Ordering::Acquire),
            "packet_threads_joined":false})
    }
}

struct Session {
    epoch: u64,
    config: TunConfig,
    dns: TunDns,
    packets: Option<(std::fs::File, std::fs::File)>,
    bridge: Option<Bridge>,
}

impl Session {
    fn start(
        epoch: u64,
        mtu: usize,
        tcp: usize,
        udp: usize,
        resources: InheritedPacketHandles,
    ) -> io::Result<Self> {
        if !(1280..=9000).contains(&mtu) || !(1..=1024).contains(&tcp) || !(1..=512).contains(&udp)
        {
            return Err(invalid("PacketWorkerLimits"));
        }
        let config = TunConfig {
            mtu,
            max_tcp_flows: tcp,
            max_udp_endpoints: udp,
            ..TunConfig::default()
        };
        config.validate()?;
        let PacketWorkerResources {
            packet_input,
            packet_output,
            fake_ip_journal,
        } = clone_inherited_packet_resources(resources)?;
        let dns = TunDns::new(FakeIpStore::from_file(fake_ip_journal, 16384).map_err(invalid)?);
        Ok(Self {
            epoch,
            config,
            dns,
            packets: Some((packet_input, packet_output)),
            bridge: None,
        })
    }

    fn bridge_start(
        &mut self,
        controller: &Controller,
        handle: &str,
        epoch: &str,
    ) -> io::Result<()> {
        if self.bridge.is_some() {
            return Err(invalid("PacketWorkerBridgeExists"));
        }
        let core = controller
            .cores_v2
            .get(&decimal(handle).map_err(invalid)?)
            .ok_or_else(|| invalid("InvalidHandle"))?;
        if core.epoch() != decimal(epoch).map_err(invalid)? {
            return Err(invalid("EngineEpochMismatch"));
        }
        let dispatcher = core.flow_dispatcher().map_err(invalid)?;
        let runtime = dispatcher.runtime_handle();
        let packets = self
            .packets
            .take()
            .ok_or_else(|| invalid("PacketWorkerResourcesConsumed"))?;
        let bridge =
            swirl_core::native_tun::spawn(dispatcher, self.dns.clone(), self.config.clone())
                .map_err(invalid)?;
        self.bridge = Some(Bridge::start(
            bridge,
            runtime,
            packets,
            self.epoch,
            self.config.mtu,
        )?);
        Ok(())
    }
}

fn stop(session: &mut Option<Session>, controller: &mut Controller) -> io::Result<()> {
    let result = if let Some(bridge) = session.as_mut().and_then(|session| session.bridge.as_mut())
    {
        bridge
            .runtime
            .block_on(bridge.control.shutdown())
            .map_err(invalid)
    } else {
        Ok(())
    };
    // Retain BridgeControl's NativeTunLease through Core.stop. This worker has
    // no routes/journals to restore, and never releases its physical-egress lease.
    for core in controller.cores_v2.values_mut() {
        core.stop();
    }
    result
}

fn status(session: &Option<Session>, profile: &TokenProfile, stopped: bool) -> Value {
    json!({"state":if stopped { "stopped" } else if session.as_ref().is_some_and(|s| s.bridge.is_some()) { "running" } else { "ready" },
        "token_validated":true,"token_profile":profile,
        "bridge":session.as_ref().and_then(|session|session.bridge.as_ref()).map(Bridge::status),
        "physical_egress_suspended":true,"broker_authenticated":false,"service_principal_authenticated":false,
        "kernel_identity_enforced":false,"product_broker_integrated":false,"system_kill_switch":false,
        "network_resources_owned":false,"routes_restored":false,
        "source_sha":option_env!("SWIRL_SOURCE_SHA").unwrap_or("unrecorded")})
}

/// Only the exact internal bin should invoke this endpoint. An actual restricted
/// token is required, but is not sufficient to authenticate a production broker.
pub fn run() -> io::Result<()> {
    // Inherited packet resources are outside the private TCP socket quota.
    swirl_transport::egress::check_unmetered_egress()?;
    let profile = current_token_profile()?;
    token_gate(&profile)?;
    let _egress = EgressLease::acquire_suspended()?;
    let mut controller = Controller::default();
    let mut session = None;
    let (commands, incoming) = mpsc::sync_channel(1);
    thread::Builder::new()
        .name("swirl-packet-control".into())
        .spawn(move || {
            let stdin = io::stdin();
            let mut input = stdin.lock();
            loop {
                let frame = read_frame(&mut input);
                let terminal = !matches!(frame, Ok(Some(_)));
                if commands.send(frame).is_err() || terminal {
                    break;
                }
            }
        })?;
    let mut output = BoundedOutput::new(emit)?;
    let mut heartbeat_at = Instant::now();
    let outcome = (|| {
        loop {
            if let Some(bridge) = session.as_ref().and_then(|s: &Session| s.bridge.as_ref()) {
                if let Ok(error) = bridge.errors.try_recv() {
                    return Err(error);
                }
                if bridge.control.is_finished() {
                    return Err(io::Error::other("PacketWorkerBridgeStopped"));
                }
            }
            if let Some(session) = &session
                && Instant::now() >= heartbeat_at
            {
                output.write(json!({"packet_worker_schema":1,"event":"heartbeat","epoch":session.epoch,"state":if session.bridge.is_some() {"running"} else {"ready"}}), OUTPUT_DRAIN)?;
                heartbeat_at = Instant::now() + Duration::from_secs(1);
            }
            let bytes = match incoming.recv_timeout(Duration::from_millis(100)) {
                Ok(Ok(Some(bytes))) => bytes,
                Ok(Ok(None)) | Err(mpsc::RecvTimeoutError::Disconnected) => {
                    return Err(io::Error::new(
                        io::ErrorKind::UnexpectedEof,
                        "PacketWorkerControlClosed",
                    ));
                }
                Ok(Err(error)) => return Err(error),
                Err(mpsc::RecvTimeoutError::Timeout) => continue,
            };
            let request = request(&bytes, session.as_ref().map(|s| s.epoch))?;
            let stopped = matches!(request.command, Command::Stop {});
            let result = (|| match request.command {
                Command::Init {
                    mtu,
                    max_tcp_flows,
                    max_udp_flows,
                    resources,
                } if session.is_none() => {
                    session = Some(Session::start(
                        request.epoch,
                        mtu,
                        max_tcp_flows,
                        max_udp_flows,
                        resources,
                    )?);
                    Ok(status(&session, &profile, false))
                }
                _ if session.is_none() => Err(invalid("PacketWorkerInitRequired")),
                Command::Init { .. } => Err(invalid("PacketWorkerAlreadyInitialized")),
                Command::Core { json } => {
                    core_command(&json, &request.request_id, controller.cores_v2.len())?;
                    Ok(controller.dispatch(json.as_bytes()))
                }
                Command::BridgeStart {
                    handle,
                    engine_epoch,
                } => {
                    session
                        .as_mut()
                        .unwrap()
                        .bridge_start(&controller, &handle, &engine_epoch)?;
                    Ok(status(&session, &profile, false))
                }
                Command::Status {} => Ok(status(&session, &profile, false)),
                Command::Stop {} => {
                    stop(&mut session, &mut controller)?;
                    Ok(status(&session, &profile, true))
                }
            })();
            let ok = result
                .as_ref()
                .is_ok_and(|value| value["ok"].as_bool() != Some(false));
            let reply = match &result {
                Ok(value) => value.clone(),
                Err(error) => json!({"error":error.to_string()}),
            };
            output.write(json!({"packet_worker_schema":1,"request_id":request.request_id,"epoch":request.epoch,"ok":ok,"result":reply}), OUTPUT_DRAIN)?;
            result?;
            if !ok {
                return Err(io::Error::other("PacketWorkerCoreFailed"));
            }
            if stopped {
                return Ok(());
            }
        }
    })();
    let cleanup = stop(&mut session, &mut controller);
    // Blocking input/output pipe threads are process-owned and may still wait
    // for the parent. The parent's job/deadline and process exit close them.
    // No join or OS-network restoration claim is made by the Stop response.
    match (outcome, cleanup) {
        (Err(primary), Err(cleanup)) => {
            eprintln!("packet worker secondary cleanup failure: {cleanup}");
            Err(primary)
        }
        (Err(primary), Ok(())) => Err(primary),
        (Ok(()), cleanup) => cleanup,
    }
}

#[cfg(test)]
#[path = "native_packet_worker_tests.rs"]
mod tests;

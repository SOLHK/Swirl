//! A short-lived authenticated CONNECT tunnel for one explicitly chosen source.
//! Qt owns HTTPS, certificate checks, URL bytes, redirects and response limits.
use ring::rand::{SecureRandom, SystemRandom};
use serde::Deserialize;
use serde_json::json;
use std::{
    collections::HashMap,
    io,
    net::{IpAddr, SocketAddr},
    sync::{Arc, Mutex, OnceLock},
    time::Duration,
};
use swirl_subscription::Credentials;
#[cfg(any(windows, test))]
use tokio::io::AsyncReadExt;
use tokio::{
    io::AsyncWriteExt,
    net::{TcpListener, TcpSocket, TcpStream},
    runtime::{Builder, Runtime},
    task::{JoinHandle, JoinSet},
    time::{Instant, timeout, timeout_at},
};

#[derive(Clone)]
struct Endpoint {
    address: SocketAddr,
    source: IpAddr,
    interface: u32,
}
struct Route {
    host: String,
    port: u16,
    credentials: Credentials,
    endpoints: Vec<Endpoint>,
    resolved: tokio::sync::OnceCell<Result<Vec<Endpoint>, &'static str>>,
}

async fn connect(endpoint: &Endpoint) -> io::Result<TcpStream> {
    let socket = if endpoint.address.is_ipv6() {
        TcpSocket::new_v6()?
    } else {
        TcpSocket::new_v4()?
    };
    #[cfg(windows)]
    swirl_platform::pin_outbound_socket(&socket, endpoint.address.is_ipv6(), endpoint.interface)?;
    #[cfg(not(windows))]
    let _ = endpoint.interface;
    socket.bind(SocketAddr::new(endpoint.source, 0))?;
    let stream = socket.connect(endpoint.address).await?;
    if stream.local_addr()?.ip() != endpoint.source {
        return Err(io::Error::other("PhysicalSourceChanged"));
    }
    Ok(stream)
}

async fn tunnel(mut client: TcpStream, route: Arc<Route>) -> io::Result<()> {
    let request = timeout(
        Duration::from_secs(3),
        swirl_protocol::accept(&mut client, &Some(route.credentials.clone())),
    )
    .await
    .map_err(|_| io::Error::other("PhysicalRouteClientTimeout"))?
    .map_err(io::Error::other)?;
    let host_matches = match (
        request.target.host.parse::<IpAddr>(),
        route.host.parse::<IpAddr>(),
    ) {
        (Ok(actual), Ok(expected)) => actual == expected,
        (Err(_), Err(_)) => request.target.host.eq_ignore_ascii_case(&route.host),
        _ => false,
    };
    if !matches!(request.kind, swirl_protocol::InboundKind::HttpConnect)
        || !host_matches
        || request.target.port != route.port
        || request.udp
    {
        client
            .write_all(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
            .await?;
        return Err(io::Error::other("PhysicalRouteTargetRejected"));
    }
    let endpoints = route
        .resolved
        .get_or_init(|| async {
            if !route.endpoints.is_empty() {
                return Ok(route.endpoints.clone());
            }
            timeout(Duration::from_secs(10), resolve(&route.host, route.port))
                .await
                .map_err(|_| "PhysicalDnsTimeout")?
                .map_err(|_| "PhysicalDownloadUnavailable")
        })
        .await;
    let Ok(endpoints) = endpoints else {
        swirl_protocol::reply(&mut client, request.kind, false)
            .await
            .map_err(io::Error::other)?;
        return Err(io::Error::other("PhysicalDownloadUnavailable"));
    };
    let mut upstream = None;
    for endpoint in endpoints {
        if let Ok(Ok(stream)) = timeout(Duration::from_secs(5), connect(endpoint)).await {
            upstream = Some(stream);
            break;
        }
    }
    let Some(mut upstream) = upstream else {
        swirl_protocol::reply(&mut client, request.kind, false)
            .await
            .map_err(io::Error::other)?;
        return Err(io::Error::other("PhysicalRouteConnectFailed"));
    };
    swirl_protocol::reply(&mut client, request.kind, true)
        .await
        .map_err(io::Error::other)?;
    if !request.initial.is_empty() {
        upstream.write_all(&request.initial).await?;
    }
    // No HTTP or TLS parsing here. The existing relay preserves half-closes;
    // Qt performs certificate checks and stops at its response-size boundary.
    swirl_transport::relay(
        &mut client,
        &mut upstream,
        Arc::new(swirl_transport::Counters::default()),
        Arc::new(swirl_transport::Counters::default()),
    )
    .await
}

async fn serve(listener: TcpListener, route: Arc<Route>, lifetime: Duration) -> io::Result<()> {
    let deadline = Instant::now() + lifetime;
    let mut tasks = JoinSet::new();
    let mut accepted = 0;
    loop {
        tokio::select! {
            _ = tokio::time::sleep_until(deadline) => return Ok(()),
            result = tasks.join_next(), if !tasks.is_empty() => { let _ = result; },
            result = listener.accept(), if accepted < 16 && tasks.len() < 4 => {
                let (stream, peer) = result?;
                if !peer.ip().is_loopback() { continue; }
                accepted += 1;
                let route = route.clone();
                tasks.spawn(async move { let _ = timeout_at(deadline, tunnel(stream, route)).await; });
            }
        }
    }
}

fn public_destination(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(ip) => {
            let octets = ip.octets();
            !ip.is_private()
                && !ip.is_loopback()
                && !ip.is_link_local()
                && !ip.is_multicast()
                && !ip.is_unspecified()
                && !ip.is_broadcast()
                && octets[0] != 0
                && octets[0] < 240
                && !(octets[0] == 100 && (64..=127).contains(&octets[1]))
                && !(octets[0] == 198 && (18..=19).contains(&octets[1]))
        }
        IpAddr::V6(ip) => ip.to_ipv4_mapped().map_or_else(
            || {
                !ip.is_loopback()
                    && !ip.is_unspecified()
                    && !ip.is_multicast()
                    && !ip.is_unique_local()
                    && !ip.is_unicast_link_local()
                    && (ip.segments()[0] & 0xffc0) != 0xfec0
            },
            |ip| public_destination(ip.into()),
        ),
    }
}

#[cfg(windows)]
async fn resolve(host: &str, port: u16) -> io::Result<Vec<Endpoint>> {
    use swirl_platform::physical_network::physical_interfaces;
    let interfaces = physical_interfaces()?;
    let addresses = if let Ok(ip) = host.parse::<IpAddr>() {
        vec![ip]
    } else {
        let mut addresses = Vec::new();
        // Use the selected hardware adapter's configured resolver only. The
        // Windows/system resolver may be a foreign TUN fake-IP service.
        for interface in &interfaces {
            for server in &interface.dns {
                let Some(egress) = interfaces.iter().find(|entry| {
                    entry.adapter_id == interface.adapter_id
                        && entry.source.is_ipv6() == server.is_ipv6()
                }) else {
                    continue;
                };
                let endpoint = Endpoint {
                    address: SocketAddr::new(*server, 53),
                    source: egress.source,
                    interface: egress.index,
                };
                for kind in [swirl_dns::DNS_A, swirl_dns::AAAA] {
                    if let Ok(Ok(ips)) =
                        timeout(Duration::from_secs(2), query_dns(host, kind, &endpoint)).await
                    {
                        for ip in ips {
                            if !addresses.contains(&ip) {
                                addresses.push(ip);
                            }
                        }
                    }
                }
                if !addresses.is_empty() {
                    break;
                }
            }
            if !addresses.is_empty() {
                break;
            }
        }
        if addresses.is_empty() {
            return Err(io::Error::other("PhysicalDnsUnavailable"));
        }
        addresses
    };
    // Reject the whole response if one address is private/fake; do not pick a
    // seemingly safe address from a mixed DNS-rebinding answer.
    if addresses.iter().any(|ip| !public_destination(*ip)) {
        return Err(io::Error::other("PhysicalTargetNotPublic"));
    }
    let result = addresses
        .into_iter()
        .filter_map(|ip| {
            interfaces
                .iter()
                .find(|entry| entry.source.is_ipv6() == ip.is_ipv6())
                .map(|entry| Endpoint {
                    address: SocketAddr::new(ip, port),
                    source: entry.source,
                    interface: entry.index,
                })
        })
        .collect::<Vec<_>>();
    if result.is_empty() {
        return Err(io::Error::other("PhysicalNetworkUnavailable"));
    }
    Ok(result)
}

#[cfg(any(windows, test))]
async fn query_dns(host: &str, kind: u16, endpoint: &Endpoint) -> io::Result<Vec<IpAddr>> {
    let mut random = [0; 2];
    SystemRandom::new()
        .fill(&mut random)
        .map_err(|_| io::Error::other("PhysicalRandomUnavailable"))?;
    let id = u16::from_ne_bytes(random);
    let query = swirl_dns::encode_query(&swirl_dns::DnsQuestion {
        id,
        name: host.into(),
        kind,
        recursion_desired: true,
    })
    .map_err(io::Error::other)?;
    let socket = tokio::net::UdpSocket::bind(SocketAddr::new(endpoint.source, 0)).await?;
    #[cfg(windows)]
    swirl_platform::pin_outbound_socket(&socket, endpoint.address.is_ipv6(), endpoint.interface)?;
    socket.connect(endpoint.address).await?;
    socket.send(&query).await?;
    let mut response = vec![0; 4096];
    let response = match timeout(Duration::from_secs(1), socket.recv(&mut response)).await {
        Ok(Ok(length)) if length >= 12 && response[2] & 0x02 == 0 => {
            response.truncate(length);
            response
        }
        _ => query_dns_tcp(&query, endpoint).await?,
    };
    if response.get(12..query.len()) != query.get(12..) || response[2] & 0x02 != 0 {
        return Err(io::Error::other("PhysicalDnsQuestionChanged"));
    }
    let (actual, rcode, ips) = swirl_dns::decode_answers(&response).map_err(io::Error::other)?;
    if actual != id || rcode != 0 {
        return Err(io::Error::other("PhysicalDnsRejected"));
    }
    Ok(ips)
}

#[cfg(any(windows, test))]
async fn query_dns_tcp(query: &[u8], endpoint: &Endpoint) -> io::Result<Vec<u8>> {
    let mut stream = connect(endpoint).await?;
    stream
        .write_all(&swirl_dns::wrap_tcp(query).map_err(io::Error::other)?)
        .await?;
    let length = stream.read_u16().await? as usize;
    if !(12..=4096).contains(&length) {
        return Err(io::Error::other("PhysicalDnsResponseLimit"));
    }
    let mut response = vec![0; length];
    stream.read_exact(&mut response).await?;
    Ok(response)
}

#[cfg(not(windows))]
async fn resolve(_: &str, _: u16) -> io::Result<Vec<Endpoint>> {
    Err(io::Error::other("PhysicalDownloadWindowsOnly"))
}

#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
enum Command {
    Start { host: String, port: u16 },
    Stop { handle: u64 },
}
#[derive(Default)]
struct Routes {
    next: u64,
    tasks: HashMap<u64, JoinHandle<io::Result<()>>>,
}
static ROUTES: OnceLock<Mutex<Routes>> = OnceLock::new();
static RUNTIME: OnceLock<Result<Runtime, io::Error>> = OnceLock::new();
fn runtime() -> io::Result<&'static Runtime> {
    RUNTIME
        .get_or_init(|| {
            Builder::new_multi_thread()
                .worker_threads(1)
                .enable_all()
                .build()
        })
        .as_ref()
        .map_err(|_| io::Error::other("PhysicalRuntimeUnavailable"))
}

fn execute(command: Command) -> io::Result<serde_json::Value> {
    let runtime = runtime()?;
    match command {
        Command::Stop { handle } => {
            let task = ROUTES
                .get_or_init(Default::default)
                .lock()
                .map_err(|_| io::Error::other("PhysicalRouteState"))?
                .tasks
                .remove(&handle);
            if let Some(task) = task {
                task.abort();
                let _ = runtime.block_on(task);
            }
            Ok(json!({"ok":true}))
        }
        Command::Start { host, port } => {
            if port == 0
                || host.len() > 253
                || !host.is_ascii()
                || !swirl_subscription::valid_host(&host)
                || host == "localhost"
                || host.ends_with(".localhost")
            {
                return Err(io::Error::other("PhysicalRouteTargetInvalid"));
            }
            if host
                .parse::<IpAddr>()
                .is_ok_and(|ip| !public_destination(ip))
            {
                return Err(io::Error::other("PhysicalTargetNotPublic"));
            }
            if !cfg!(windows) {
                return Err(io::Error::other("PhysicalDownloadWindowsOnly"));
            }
            let mut random = [0; 32];
            SystemRandom::new()
                .fill(&mut random)
                .map_err(|_| io::Error::other("PhysicalRandomUnavailable"))?;
            let password = random
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect::<String>();
            let username = "swirl-download".to_string();
            let route = Arc::new(Route {
                host,
                port,
                credentials: Credentials {
                    username: username.clone(),
                    password: password.clone(),
                },
                endpoints: Vec::new(),
                resolved: tokio::sync::OnceCell::new(),
            });
            let listener = runtime.block_on(TcpListener::bind("127.0.0.1:0"))?;
            let port = listener.local_addr()?.port();
            let mut routes = ROUTES
                .get_or_init(Default::default)
                .lock()
                .map_err(|_| io::Error::other("PhysicalRouteState"))?;
            routes.tasks.retain(|_, task| !task.is_finished());
            if routes.tasks.len() >= 8 {
                return Err(io::Error::other("PhysicalRouteBusy"));
            }
            routes.next = routes
                .next
                .checked_add(1)
                .ok_or_else(|| io::Error::other("PhysicalRouteGeneration"))?;
            if routes.next > i64::MAX as u64 {
                return Err(io::Error::other("PhysicalRouteGeneration"));
            }
            let handle = routes.next;
            routes.tasks.insert(
                handle,
                runtime.spawn(serve(listener, route, Duration::from_secs(30))),
            );
            Ok(
                json!({"ok":true,"handle":handle,"port":port,"username":username,"password":password}),
            )
        }
    }
}

fn response(input: &[u8], capacity: usize) -> Result<(usize, Option<Vec<u8>>), isize> {
    // Starting a listener is a side effect. A size query or insufficient output
    // buffer must never create an unreachable route or rerun a start command.
    if capacity < 4096 {
        return Err(-1);
    }
    let result = serde_json::from_slice(input)
        .map_err(|_| io::Error::other("PhysicalRouteCommandInvalid"))
        .and_then(execute);
    let value = match result {
        Ok(value) => value,
        Err(error) => {
            const KNOWN: &[&str] = &[
                "PhysicalRouteTargetInvalid",
                "PhysicalDnsTimeout",
                "PhysicalDnsUnavailable",
                "PhysicalTargetNotPublic",
                "PhysicalNetworkUnavailable",
                "PhysicalDownloadWindowsOnly",
                "PhysicalRouteBusy",
                "PhysicalRouteCommandInvalid",
            ];
            let text = error.to_string();
            json!({"ok":false,"error":if KNOWN.contains(&text.as_str()){text.as_str()}else{"PhysicalDownloadUnavailable"}})
        }
    };
    crate::import_ffi::encoded_response(&value, capacity)
}

/// Fixed-capacity, single-call route control ABI. Inputs/outputs remain private.
/// # Safety
/// Caller supplies initialized input and disjoint writable output as indicated.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swirl_download_route_v1(
    input: *const u8,
    input_len: usize,
    output: *mut u8,
    capacity: usize,
) -> isize {
    unsafe { crate::import_ffi::call(input, input_len, output, capacity, 4096, response) }
}

#[cfg(test)]
#[path = "download_route_tests.rs"]
mod tests;

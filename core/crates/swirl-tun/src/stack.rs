//! smoltcp owns TCP retransmission and congestion. This module classifies
//! packets once, keeps that decision on the flow, and moves bytes through the
//! caller-supplied dispatcher.
use std::{
    collections::{HashMap, HashSet, VecDeque},
    net::{IpAddr, SocketAddr},
    sync::{Arc, Mutex},
    time::{Duration as WallDuration, Instant as Wall},
};

use smoltcp::{
    iface::{Config, Interface, SocketHandle, SocketSet, SocketStorage},
    phy::{self, Checksum, Device, DeviceCapabilities, Medium},
    socket::tcp::{self, Socket as TcpSocket},
    time::{Duration, Instant},
    wire::{HardwareAddress, IpAddress, IpCidr, IpListenEndpoint},
};
use swirl_dns::{
    AAAA, Association, DNS_A, DNS_IPV4, DNS_IPV6, TUN_IPV4, TUN_IPV6, decode_query, encode_response,
};

use crate::{
    dispatch::{Chunk, Decision, Dispatch, FlowMeta, Pull, Push, UdpPipe},
    dns_flow::{DnsAnswer, DnsReply},
    guard::{LoopGuard, LoopVerdict},
    packet::{self, Packet},
};

const QUEUE: usize = 64;
const BATCH: usize = 32;
const MAX_TCP: usize = 128;
const MAX_UDP: usize = 256;
const SOCKET_BUF: usize = 8 * 1024;
const HOLD: usize = 8;
const FAIL_TTL: WallDuration = WallDuration::from_secs(5);

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Stats {
    pub tcp_open: u64,
    pub tcp_reject: u64,
    pub tcp_fail: u64,
    pub tcp_suppressed: u64,
    pub udp_open: u64,
    pub udp_drop: u64,
    pub dns_answers: u64,
    pub leak_suppressed: u64,
    pub loop_bypass: u64,
    pub loop_reject: u64,
    pub parse_drop: u64,
}

struct Pending {
    handle: SocketHandle,
    born: Wall,
}

struct TcpFlow {
    pipe: Box<dyn crate::dispatch::Pipe>,
    source: SocketAddr,
    destination: SocketAddr,
    decision: Decision,
    outbound: VecDeque<Chunk>,
    inbound: Option<Chunk>,
    write_closed: bool,
    fin_sent: bool,
    read_closed: bool,
    kill: bool,
}

struct UdpFlow {
    pipe: Box<dyn UdpPipe>,
    source: SocketAddr,
    destination: SocketAddr,
    last: Wall,
}

struct IpDevice {
    rx: VecDeque<Vec<u8>>,
    tx: VecDeque<Vec<u8>>,
    mtu: usize,
}

impl IpDevice {
    fn new(mtu: usize) -> Self {
        Self {
            rx: VecDeque::new(),
            tx: VecDeque::new(),
            mtu,
        }
    }
}

struct OwnedRx(Vec<u8>);

impl phy::RxToken for OwnedRx {
    fn consume<R, F>(self, f: F) -> R
    where
        F: FnOnce(&[u8]) -> R,
    {
        f(&self.0)
    }
}

struct OwnedTx<'a>(&'a mut VecDeque<Vec<u8>>);

impl phy::TxToken for OwnedTx<'_> {
    fn consume<R, F>(self, len: usize, f: F) -> R
    where
        F: FnOnce(&mut [u8]) -> R,
    {
        let mut buffer = vec![0; len];
        let result = f(&mut buffer);
        self.0.push_back(buffer);
        result
    }
}

impl Device for IpDevice {
    type RxToken<'a>
        = OwnedRx
    where
        Self: 'a;
    type TxToken<'a> = OwnedTx<'a>;

    fn receive(&mut self, _timestamp: Instant) -> Option<(Self::RxToken<'_>, Self::TxToken<'_>)> {
        let packet = self.rx.pop_front()?;
        Some((OwnedRx(packet), OwnedTx(&mut self.tx)))
    }

    fn transmit(&mut self, _timestamp: Instant) -> Option<Self::TxToken<'_>> {
        Some(OwnedTx(&mut self.tx))
    }

    fn capabilities(&self) -> DeviceCapabilities {
        let mut caps = DeviceCapabilities::default();
        caps.medium = Medium::Ip;
        caps.max_transmission_unit = self.mtu;
        caps.max_burst_size = Some(BATCH);
        caps.checksum.ipv4 = Checksum::Tx;
        caps.checksum.tcp = Checksum::Tx;
        caps.checksum.udp = Checksum::Tx;
        caps.checksum.icmpv4 = Checksum::Tx;
        caps.checksum.icmpv6 = Checksum::Tx;
        caps
    }
}

pub struct Engine {
    iface: Interface,
    device: IpDevice,
    sockets: SocketSet<'static>,
    live: HashSet<SocketHandle>,
    now: Instant,
    queue: VecDeque<Vec<u8>>,
    pending: HashMap<(SocketAddr, SocketAddr), Pending>,
    flows: HashMap<SocketHandle, TcpFlow>,
    udp: HashMap<(SocketAddr, SocketAddr), UdpFlow>,
    failed: HashMap<(SocketAddr, SocketAddr), Wall>,
    closing: Vec<SocketHandle>,
    dispatch: Box<dyn Dispatch>,
    dns: Box<dyn DnsAnswer>,
    association: Arc<Mutex<Association>>,
    guard: LoopGuard,
    leak_protection: bool,
    running: bool,
    ident: u16,
    stats: Stats,
}

impl Engine {
    pub fn new(
        dispatch: Box<dyn Dispatch>,
        dns: Box<dyn DnsAnswer>,
        association: Arc<Mutex<Association>>,
        guard: LoopGuard,
        leak_protection: bool,
    ) -> Result<Self, &'static str> {
        let mut device = IpDevice::new(1500);
        let mut config = Config::new(HardwareAddress::Ip);
        config.random_seed = 0x5357_4952;
        let now = Instant::ZERO;
        let mut iface = Interface::new(config, &mut device, now);
        // AnyIP accepts a destination when the default route's gateway is one
        // of our addresses. That is the whole TUN prefix, not a second stack.
        iface.set_any_ip(true);
        let mut address_full = false;
        iface.update_ip_addrs(|addrs| {
            address_full |= addrs
                .push(IpCidr::new(IpAddress::Ipv4(TUN_IPV4), 15))
                .is_err();
            address_full |= addrs
                .push(IpCidr::new(IpAddress::Ipv6(TUN_IPV6), 48))
                .is_err();
        });
        if address_full {
            return Err("TunAddressTable");
        }
        iface
            .routes_mut()
            .add_default_ipv4_route(TUN_IPV4)
            .map_err(|_| "TunRouteTable")?;
        iface
            .routes_mut()
            .add_default_ipv6_route(TUN_IPV6)
            .map_err(|_| "TunRouteTable")?;
        Ok(Self {
            iface,
            device,
            sockets: SocketSet::new(Vec::<SocketStorage>::new()),
            live: HashSet::new(),
            now,
            queue: VecDeque::new(),
            pending: HashMap::new(),
            flows: HashMap::new(),
            udp: HashMap::new(),
            failed: HashMap::new(),
            closing: Vec::new(),
            dispatch,
            dns,
            association,
            guard,
            leak_protection,
            running: true,
            ident: 1,
            stats: Stats::default(),
        })
    }

    pub fn stats(&self) -> &Stats {
        &self.stats
    }

    pub fn tcp_flows(&self) -> usize {
        self.flows.len()
    }

    pub fn udp_sessions(&self) -> usize {
        self.udp.len()
    }

    pub fn ingress_len(&self) -> usize {
        self.queue.len()
    }

    pub fn advance(&mut self, millis: u64) {
        self.now += Duration::from_millis(millis);
    }

    pub fn push(&mut self, packet: &[u8]) -> Result<(), &'static str> {
        if !self.running {
            return Err("TunStopped");
        }
        if packet.is_empty() || packet.len() > 1500 {
            return Err("TunPacketLength");
        }
        if self.queue.len() >= QUEUE {
            return Err("TunIngressFull");
        }
        self.queue.push_back(packet.to_vec());
        Ok(())
    }

    pub fn stop(&mut self) {
        self.running = false;
        self.queue.clear();
    }

    pub fn revoke_node(&mut self, node: &str) {
        for flow in self.flows.values_mut() {
            if flow.decision.node_id == node {
                flow.kill = true;
            }
        }
    }

    pub fn poll(&mut self) -> Vec<Vec<u8>> {
        if !self.running {
            return Vec::new();
        }
        let mut batch = Vec::new();
        while batch.len() < BATCH {
            let Some(packet) = self.queue.pop_front() else {
                break;
            };
            batch.push(packet);
        }
        let mut replies = Vec::new();
        for packet in batch {
            self.ingest(&packet, &mut replies);
        }
        self.drive();
        self.promote();
        self.service_tcp();
        self.pull_udp(&mut replies);
        self.reap_pending();
        self.reap_udp();
        self.drive();
        self.retire();
        replies.extend(self.device.tx.drain(..));
        replies
    }

    fn ingest(&mut self, packet: &[u8], replies: &mut Vec<Vec<u8>>) {
        let parsed = match packet::parse(packet) {
            Ok(parsed) => parsed,
            Err(_) => {
                self.stats.parse_drop += 1;
                return;
            }
        };
        if let Packet::Udp {
            source,
            destination,
            payload,
        } = &parsed
            && self.capture_dns(*destination)
        {
            if destination.ip() != IpAddr::V4(DNS_IPV4) && destination.ip() != IpAddr::V6(DNS_IPV6)
            {
                self.stats.leak_suppressed += 1;
            }
            if let Some(reply) = self.answer_dns(*source, *destination, payload) {
                replies.push(reply);
            }
            return;
        }
        let destination = match &parsed {
            Packet::Tcp { destination, .. } | Packet::Udp { destination, .. } => *destination,
            Packet::Other => return,
        };
        match self.guard.check(destination.ip()) {
            LoopVerdict::Bypass => {
                self.stats.loop_bypass += 1;
                return;
            }
            LoopVerdict::Reject => {
                self.stats.loop_reject += 1;
                return;
            }
            LoopVerdict::Forward => {}
        }
        match parsed {
            Packet::Tcp {
                source,
                destination,
                syn,
                ack,
            } if syn && !ack => {
                if self.prepare_tcp(source, destination) {
                    self.device.rx.push_back(packet.to_vec());
                }
            }
            Packet::Tcp { .. } => self.device.rx.push_back(packet.to_vec()),
            Packet::Udp {
                source,
                destination,
                payload,
            } => self.on_udp(source, destination, &payload),
            Packet::Other => {}
        }
    }

    fn capture_dns(&self, destination: SocketAddr) -> bool {
        destination.port() == 53
            && (self.leak_protection
                || destination.ip() == IpAddr::V4(DNS_IPV4)
                || destination.ip() == IpAddr::V6(DNS_IPV6))
    }

    fn answer_dns(
        &mut self,
        source: SocketAddr,
        destination: SocketAddr,
        payload: &[u8],
    ) -> Option<Vec<u8>> {
        let Ok(question) = decode_query(payload) else {
            self.stats.parse_drop += 1;
            return None;
        };
        let body = if question.kind != DNS_A && question.kind != AAAA {
            encode_response(&question, &[], 0, 4)
        } else {
            match self.dns.answer(&question.name, question.kind, Wall::now()) {
                Ok(DnsReply::Addresses(ips)) => encode_response(&question, &ips, 60, 0),
                Ok(DnsReply::NameError) => encode_response(&question, &[], 0, 3),
                Err(_) => encode_response(&question, &[], 0, 2),
            }
        };
        let Ok(body) = body else {
            self.stats.parse_drop += 1;
            return None;
        };
        self.stats.dns_answers += 1;
        packet::udp(destination, source, &body, next_ident(&mut self.ident)).ok()
    }

    fn prepare_tcp(&mut self, source: SocketAddr, destination: SocketAddr) -> bool {
        let key = (source, destination);
        if self
            .failed
            .get(&key)
            .is_some_and(|born| born.elapsed() < FAIL_TTL)
        {
            self.stats.tcp_suppressed += 1;
            return false;
        }
        if self.pending.contains_key(&key)
            || self
                .flows
                .values()
                .any(|flow| flow.source == source && flow.destination == destination)
        {
            return true;
        }
        if self.pending.len() + self.flows.len() >= MAX_TCP {
            self.stats.tcp_fail += 1;
            return false;
        }
        let mut socket = TcpSocket::new(
            tcp::SocketBuffer::new(vec![0; SOCKET_BUF]),
            tcp::SocketBuffer::new(vec![0; SOCKET_BUF]),
        );
        socket.set_nagle_enabled(false);
        socket.set_ack_delay(None);
        let listen = IpListenEndpoint {
            addr: Some(destination.ip().into()),
            port: destination.port(),
        };
        if socket.listen(listen).is_err() {
            self.stats.tcp_fail += 1;
            return false;
        }
        let handle = self.add_socket(socket);
        self.pending.insert(
            key,
            Pending {
                handle,
                born: Wall::now(),
            },
        );
        true
    }

    fn on_udp(&mut self, source: SocketAddr, destination: SocketAddr, payload: &[u8]) {
        let key = (source, destination);
        if !self.udp.contains_key(&key) {
            if self.udp.len() >= MAX_UDP {
                self.stats.udp_drop += 1;
                return;
            }
            let meta = self.meta(source, destination);
            match self.dispatch.open_udp(&meta) {
                Ok(pipe) => {
                    self.stats.udp_open += 1;
                    self.udp.insert(
                        key,
                        UdpFlow {
                            pipe,
                            source,
                            destination,
                            last: Wall::now(),
                        },
                    );
                }
                Err(_) => {
                    self.stats.udp_drop += 1;
                    return;
                }
            }
        }
        let Some(flow) = self.udp.get_mut(&key) else {
            return;
        };
        flow.last = Wall::now();
        if !flow.pipe.push(payload) {
            self.stats.udp_drop += 1;
        }
    }

    fn promote(&mut self) {
        let ready: Vec<(SocketAddr, SocketAddr, SocketHandle)> = self
            .pending
            .iter()
            .filter_map(|(&(source, destination), pending)| {
                let state = self.sockets.get::<TcpSocket>(pending.handle).state();
                (state == tcp::State::Established).then_some((source, destination, pending.handle))
            })
            .collect();
        for (source, destination, handle) in ready {
            self.pending.remove(&(source, destination));
            let meta = self.meta(source, destination);
            match self.dispatch.open_tcp(&meta) {
                Ok((decision, pipe)) if decision.action != crate::dispatch::Action::Reject => {
                    self.stats.tcp_open += 1;
                    self.flows.insert(
                        handle,
                        TcpFlow {
                            pipe,
                            source,
                            destination,
                            decision,
                            outbound: VecDeque::new(),
                            inbound: None,
                            write_closed: false,
                            fin_sent: false,
                            read_closed: false,
                            kill: false,
                        },
                    );
                }
                Ok(_) => self.fail_tcp(handle, source, destination, true),
                Err(code) => self.fail_tcp(handle, source, destination, code == "Rejected"),
            }
        }
    }

    fn fail_tcp(
        &mut self,
        handle: SocketHandle,
        source: SocketAddr,
        destination: SocketAddr,
        reject: bool,
    ) {
        if self.live.contains(&handle) {
            self.sockets.get_mut::<TcpSocket>(handle).abort();
        }
        self.closing.push(handle);
        self.failed.insert((source, destination), Wall::now());
        if self.failed.len() > 128 {
            self.failed.clear();
            self.failed.insert((source, destination), Wall::now());
        }
        if reject {
            self.stats.tcp_reject += 1;
        } else {
            self.stats.tcp_fail += 1;
        }
    }

    fn service_tcp(&mut self) {
        let sockets = &mut self.sockets;
        let flows = &mut self.flows;
        let mut finished = Vec::new();
        for (handle, flow) in flows.iter_mut() {
            if service_socket(sockets, *handle, flow) {
                finished.push(*handle);
            }
        }
        for handle in finished {
            self.flows.remove(&handle);
            self.closing.push(handle);
        }
    }

    fn pull_udp(&mut self, replies: &mut Vec<Vec<u8>>) {
        let ident = &mut self.ident;
        for flow in self.udp.values_mut() {
            while let Some(reply) = flow.pipe.pull() {
                if let Ok(packet) = packet::udp(
                    flow.destination,
                    flow.source,
                    &reply.payload,
                    next_ident(ident),
                ) {
                    replies.push(packet);
                }
            }
        }
    }

    fn reap_pending(&mut self) {
        let stale: Vec<((SocketAddr, SocketAddr), SocketHandle)> = self
            .pending
            .iter()
            .filter_map(|(key, pending)| {
                let state = self.sockets.get::<TcpSocket>(pending.handle).state();
                let stale = pending.born.elapsed() > WallDuration::from_secs(30)
                    || !matches!(
                        state,
                        tcp::State::Listen | tcp::State::SynReceived | tcp::State::Established
                    );
                stale.then_some((*key, pending.handle))
            })
            .collect();
        for (key, handle) in stale {
            self.pending.remove(&key);
            if self.live.contains(&handle) {
                self.sockets.get_mut::<TcpSocket>(handle).abort();
            }
            self.closing.push(handle);
        }
    }

    fn reap_udp(&mut self) {
        self.udp
            .retain(|_, flow| flow.last.elapsed() < WallDuration::from_secs(30));
    }

    fn retire(&mut self) {
        let closing = std::mem::take(&mut self.closing);
        let mut seen = HashSet::new();
        for handle in closing {
            if !seen.insert(handle) || !self.live.contains(&handle) {
                continue;
            }
            let state = self.sockets.get::<TcpSocket>(handle).state();
            if matches!(state, tcp::State::Closed | tcp::State::TimeWait) {
                self.drop_socket(handle);
            } else {
                self.closing.push(handle);
            }
        }
    }

    fn meta(&self, source: SocketAddr, destination: SocketAddr) -> FlowMeta {
        FlowMeta {
            source,
            destination,
            domain: self.domain_of(destination.ip()),
        }
    }

    fn domain_of(&self, ip: IpAddr) -> Option<String> {
        self.association
            .lock()
            .ok()?
            .lookup(ip, Wall::now())
            .map(str::to_owned)
    }

    fn drive(&mut self) {
        let _ = self
            .iface
            .poll(self.now, &mut self.device, &mut self.sockets);
    }

    fn add_socket(&mut self, socket: TcpSocket<'static>) -> SocketHandle {
        let handle = self.sockets.add(socket);
        self.live.insert(handle);
        handle
    }

    fn drop_socket(&mut self, handle: SocketHandle) {
        if self.live.remove(&handle) {
            self.sockets.remove(handle);
            self.flows.remove(&handle);
        }
    }
}

fn next_ident(ident: &mut u16) -> u16 {
    let value = *ident;
    *ident = ident.wrapping_add(1);
    if *ident == 0 {
        *ident = 1;
    }
    value
}

fn service_socket(sockets: &mut SocketSet<'_>, handle: SocketHandle, flow: &mut TcpFlow) -> bool {
    let sock = sockets.get_mut::<TcpSocket>(handle);
    if flow.kill {
        sock.abort();
        return true;
    }
    if !flow.write_closed {
        while flow.outbound.len() < HOLD {
            match flow.pipe.pull_downstream() {
                Pull::Empty => break,
                Pull::Closed | Pull::Chunk(Chunk::Shutdown) => {
                    flow.write_closed = true;
                    break;
                }
                Pull::Chunk(chunk) => flow.outbound.push_back(chunk),
            }
        }
    }
    loop {
        let sent = match flow.outbound.front() {
            Some(Chunk::Data(buf)) => match sock.send_slice(buf) {
                Ok(n) => n,
                Err(_) => {
                    sock.abort();
                    return true;
                }
            },
            Some(Chunk::Shutdown) => {
                flow.outbound.pop_front();
                flow.write_closed = true;
                continue;
            }
            None => break,
        };
        if sent == 0 {
            break;
        }
        let finished = match flow.outbound.front_mut() {
            Some(Chunk::Data(buf)) if sent >= buf.len() => true,
            Some(Chunk::Data(buf)) => {
                buf.drain(..sent);
                false
            }
            _ => false,
        };
        if finished {
            flow.outbound.pop_front();
        } else {
            break;
        }
    }
    if flow.write_closed && flow.outbound.is_empty() && !flow.fin_sent {
        sock.close();
        flow.fin_sent = true;
    }
    if flow.inbound.is_none() && !flow.read_closed && (sock.can_recv() || !sock.may_recv()) {
        let mut buf = [0; 2048];
        match sock.recv_slice(&mut buf) {
            Ok(0) => {}
            Ok(n) => match flow.pipe.push_upstream(Chunk::Data(buf[..n].to_vec())) {
                Push::Queued => {}
                Push::Full(chunk) => flow.inbound = Some(chunk),
                Push::Closed => {
                    sock.abort();
                    return true;
                }
            },
            Err(tcp::RecvError::Finished) => match flow.pipe.push_upstream(Chunk::Shutdown) {
                Push::Queued => flow.read_closed = true,
                Push::Full(_) => {}
                Push::Closed => {
                    sock.abort();
                    return true;
                }
            },
            Err(_) => {
                sock.abort();
                return true;
            }
        }
    } else if let Some(chunk) = flow.inbound.take() {
        match flow.pipe.push_upstream(chunk) {
            Push::Queued => {}
            Push::Full(chunk) => flow.inbound = Some(chunk),
            Push::Closed => {
                sock.abort();
                return true;
            }
        }
    }
    flow.read_closed && flow.write_closed && flow.outbound.is_empty() && flow.inbound.is_none()
}

/// In-memory host used by simulated acceptance. It does not open a NIC.
pub struct VirtualClient {
    iface: Interface,
    device: IpDevice,
    sockets: SocketSet<'static>,
    handle: SocketHandle,
    now: Instant,
    queue: VecDeque<Vec<u8>>,
}

impl VirtualClient {
    pub fn connect(source: SocketAddr, destination: SocketAddr) -> Result<Self, &'static str> {
        let mut device = IpDevice::new(1500);
        let mut config = Config::new(HardwareAddress::Ip);
        config.random_seed = 0x434c_4945;
        let now = Instant::ZERO;
        let mut iface = Interface::new(config, &mut device, now);
        let prefix = if source.is_ipv4() { 24 } else { 64 };
        let gateway = match source.ip() {
            IpAddr::V4(ip) => IpAddr::V4(std::net::Ipv4Addr::new(
                ip.octets()[0],
                ip.octets()[1],
                ip.octets()[2],
                1,
            )),
            IpAddr::V6(_) => IpAddr::V6(std::net::Ipv6Addr::LOCALHOST),
        };
        let mut full = false;
        iface.update_ip_addrs(|addrs| {
            full |= addrs.push(IpCidr::new(source.ip().into(), prefix)).is_err();
        });
        if full {
            return Err("TunAddressTable");
        }
        match gateway {
            IpAddr::V4(ip) => iface
                .routes_mut()
                .add_default_ipv4_route(ip)
                .map_err(|_| "TunRouteTable")?,
            IpAddr::V6(ip) => iface
                .routes_mut()
                .add_default_ipv6_route(ip)
                .map_err(|_| "TunRouteTable")?,
        };
        let mut socket = TcpSocket::new(
            tcp::SocketBuffer::new(vec![0; SOCKET_BUF]),
            tcp::SocketBuffer::new(vec![0; SOCKET_BUF]),
        );
        socket.set_nagle_enabled(false);
        socket.set_ack_delay(None);
        socket
            .connect(iface.context(), destination, source)
            .map_err(|_| "TunClientConnect")?;
        let mut sockets = SocketSet::new(Vec::<SocketStorage>::new());
        let handle = sockets.add(socket);
        Ok(Self {
            iface,
            device,
            sockets,
            handle,
            now,
            queue: VecDeque::new(),
        })
    }

    pub fn push(&mut self, packet: &[u8]) {
        self.queue.push_back(packet.to_vec());
    }

    pub fn poll(&mut self) -> Vec<Vec<u8>> {
        while let Some(packet) = self.queue.pop_front() {
            self.device.rx.push_back(packet);
        }
        let _ = self
            .iface
            .poll(self.now, &mut self.device, &mut self.sockets);
        self.device.tx.drain(..).collect()
    }

    pub fn advance(&mut self, millis: u64) {
        self.now += Duration::from_millis(millis);
    }

    pub fn established(&self) -> bool {
        self.sockets.get::<TcpSocket>(self.handle).state() == tcp::State::Established
    }

    pub fn send(&mut self, data: &[u8]) -> usize {
        self.sockets
            .get_mut::<TcpSocket>(self.handle)
            .send_slice(data)
            .unwrap_or(0)
    }

    pub fn recv(&mut self) -> Vec<u8> {
        let sock = self.sockets.get_mut::<TcpSocket>(self.handle);
        if !sock.can_recv() {
            return Vec::new();
        }
        let mut buf = vec![0; SOCKET_BUF];
        let n = sock.recv_slice(&mut buf).unwrap_or(0);
        buf.truncate(n);
        buf
    }
}

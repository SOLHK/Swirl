use crate::{
    Counters, TcpFlow, TunConfig, TunTcpStream, UdpDatagram,
    device::PacketDevice,
    ipv6::{Reassembler, UdpFragments},
    packet,
};
use ring::rand::{SecureRandom, SystemRandom};
use smoltcp::{
    iface::{Config, Interface, PollIngressSingleResult, SocketHandle, SocketSet},
    socket::{tcp, udp},
    time::Instant as StackInstant,
    wire::{HardwareAddress, IpCidr},
};
use std::{
    collections::HashMap,
    future::poll_fn,
    io,
    net::{Ipv4Addr, Ipv6Addr, SocketAddr},
    pin::Pin,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    task::{Context, Poll},
    time::{Duration, Instant},
};
use tokio::{
    io::{AsyncRead, AsyncWrite, DuplexStream, ReadBuf},
    sync::{Notify, mpsc, watch},
};

const PACKET_BATCH: usize = 32;
const STREAM_BATCH: usize = 16 * 1024;
const UDP_PACKET_SLOTS: usize = 16;
type FlowKey = (SocketAddr, SocketAddr);

struct TcpEntry {
    handle: SocketHandle,
    bridge: DuplexStream,
    accepted: Option<TunTcpStream>,
    abort: Arc<AtomicBool>,
    read_eof: bool,
    write_eof: bool,
    established: bool,
    created: Instant,
    activity: Instant,
}

struct UdpEntry {
    handle: SocketHandle,
    activity: Instant,
}

pub(crate) struct Driver {
    config: TunConfig,
    device: PacketDevice,
    iface: Interface,
    sockets: SocketSet<'static>,
    tcp: HashMap<FlowKey, TcpEntry>,
    udp: HashMap<SocketAddr, UdpEntry>,
    tcp_tx: mpsc::Sender<TcpFlow>,
    udp_tx: mpsc::Sender<UdpDatagram>,
    counters: Arc<Counters>,
    start: Instant,
    last_cleanup: Instant,
    ipv6_reply: Option<UdpFragments>,
    fragment_id: u32,
    ipv6_input: Reassembler,
    wake: Arc<Notify>,
}

impl Driver {
    pub fn new(
        config: TunConfig,
        output: mpsc::Sender<Vec<u8>>,
        tcp_tx: mpsc::Sender<TcpFlow>,
        udp_tx: mpsc::Sender<UdpDatagram>,
        counters: Arc<Counters>,
    ) -> io::Result<Self> {
        let mut seed = [0; 8];
        SystemRandom::new()
            .fill(&mut seed)
            .map_err(|_| io::Error::other("TUN TCP sequence seed unavailable"))?;
        let mut interface_config = Config::new(HardwareAddress::Ip);
        interface_config.random_seed = u64::from_ne_bytes(seed);
        let mut device = PacketDevice::new(output, config.mtu);
        let mut iface = Interface::new(interface_config, &mut device, StackInstant::from_millis(0));
        let v4 = Ipv4Addr::new(198, 18, 0, 1);
        let v6 = Ipv6Addr::new(0xfd53, 0x7769, 0x726c, 0, 0, 0, 0, 1);
        let mut address_error = false;
        iface.update_ip_addrs(|addresses| {
            address_error |= addresses.push(IpCidr::new(v4.into(), 32)).is_err();
            address_error |= addresses.push(IpCidr::new(v6.into(), 128)).is_err();
        });
        if address_error {
            return Err(io::Error::other("smoltcp address capacity"));
        }
        iface
            .routes_mut()
            .add_default_ipv4_route(v4)
            .map_err(io::Error::other)?;
        iface
            .routes_mut()
            .add_default_ipv6_route(v6)
            .map_err(io::Error::other)?;
        iface.set_any_ip(true);
        let start = Instant::now();
        Ok(Self {
            config,
            device,
            iface,
            sockets: SocketSet::new(Vec::new()),
            tcp: HashMap::new(),
            udp: HashMap::new(),
            tcp_tx,
            udp_tx,
            counters,
            start,
            last_cleanup: start,
            ipv6_reply: None,
            ipv6_input: Reassembler::new(),
            wake: Arc::new(Notify::new()),
            fragment_id: u32::from_ne_bytes(seed[..4].try_into().map_err(io::Error::other)?),
        })
    }

    pub async fn run(
        mut self,
        mut input: mpsc::Receiver<Vec<u8>>,
        mut replies: mpsc::Receiver<UdpDatagram>,
        mut stop: watch::Receiver<bool>,
    ) -> io::Result<()> {
        loop {
            if *stop.borrow() || self.device.outgoing.is_closed() {
                break;
            }
            self.emit_ipv6_fragment();
            self.poll_stack();
            self.collect_accepts();
            self.collect_udp();
            self.cleanup();
            let timestamp = self.timestamp();
            let mut delay = self
                .iface
                .poll_delay(timestamp, &self.sockets)
                .map(|v| Duration::from_millis(v.total_millis()))
                .unwrap_or(Duration::from_secs(1))
                .min(Duration::from_secs(1));
            if self.ipv6_reply.is_some() {
                delay = Duration::ZERO;
            }
            let wake = self.wake.clone();
            let output = self.device.outgoing.clone();
            let blocked_output = output.capacity() == 0;
            enum Event {
                Input(Option<Vec<u8>>),
                Reply(Option<UdpDatagram>),
                Bridge,
                Tick,
                Stop,
            }
            let event = tokio::select! {
                result = stop.changed() => { let _ = result; Event::Stop },
                value = input.recv(), if self.device.incoming.len() < PACKET_BATCH => Event::Input(value),
                value = replies.recv(), if self.ipv6_reply.is_none() && (!replies.is_closed() || !replies.is_empty()) => Event::Reply(value),
                _ = poll_fn(|cx| self.poll_bridges(cx)) => Event::Bridge,
                _ = wake.notified() => Event::Bridge,
                permit = output.reserve(), if blocked_output => { drop(permit); Event::Tick },
                _ = tokio::time::sleep(delay), if !blocked_output => Event::Tick,
            };
            match event {
                Event::Input(Some(bytes)) => self.ingest(bytes),
                Event::Input(None) | Event::Stop => break,
                Event::Reply(Some(datagram)) => self.reply(datagram),
                Event::Reply(None) | Event::Bridge | Event::Tick => {}
            }
            // A busy network or immediately-ready stream must not monopolize a
            // Tokio worker. Every poll batch and per-flow byte transfer is bounded.
            tokio::task::yield_now().await;
        }
        Ok(())
    }

    fn timestamp(&self) -> StackInstant {
        StackInstant::from_millis(self.start.elapsed().as_millis().min(i64::MAX as u128) as i64)
    }

    fn ingest(&mut self, bytes: Vec<u8>) {
        self.counters
            .received_packets
            .fetch_add(1, Ordering::Relaxed);
        let bytes = match self.ipv6_input.ingest(bytes) {
            Ok(Some(bytes)) => bytes,
            Ok(None) => return,
            Err(()) => {
                self.counters
                    .malformed_packets
                    .fetch_add(1, Ordering::Relaxed);
                return;
            }
        };
        let Ok(metadata) = packet::inspect(&bytes) else {
            self.counters
                .malformed_packets
                .fetch_add(1, Ordering::Relaxed);
            return;
        };
        if let Some(key) = metadata.tcp_key
            && let Some(entry) = self.tcp.get_mut(&key)
        {
            entry.activity = Instant::now();
        }
        if let Some(key) = metadata.new_tcp
            && !self.tcp.contains_key(&key)
        {
            self.admit_tcp(key);
        }
        if let Some(destination) = metadata.udp_destination {
            self.admit_udp(destination);
        }
        self.device.incoming.push_back(bytes);
        // Process each newly-admitted SYN before admitting another SYN to the
        // same destination. A listening socket cannot accidentally consume the
        // next client's tuple before becoming SynReceived.
        self.poll_stack();
    }

    fn admit_tcp(&mut self, key: FlowKey) {
        if self.tcp.len() >= self.config.max_tcp_flows || self.tcp_tx.capacity() == 0 {
            self.counters
                .rejected_tcp_flows
                .fetch_add(1, Ordering::Relaxed);
            return;
        }
        let mut socket = tcp::Socket::new(
            tcp::SocketBuffer::new(vec![0; self.config.tcp_buffer_bytes]),
            tcp::SocketBuffer::new(vec![0; self.config.tcp_buffer_bytes]),
        );
        // The destination address is required here. Binding only the port would
        // allow connections for different fake/real IPs to be misassociated.
        if socket.listen(key.1).is_err() {
            self.counters
                .rejected_tcp_flows
                .fetch_add(1, Ordering::Relaxed);
            return;
        }
        socket.set_nagle_enabled(false);
        let (stream, bridge) = tokio::io::duplex(self.config.tcp_buffer_bytes);
        let abort = Arc::new(AtomicBool::new(false));
        let stream = TunTcpStream {
            inner: stream,
            abort: abort.clone(),
            wake: self.wake.clone(),
            graceful: false,
        };
        let handle = self.sockets.add(socket);
        let now = Instant::now();
        self.tcp.insert(
            key,
            TcpEntry {
                handle,
                bridge,
                abort,
                accepted: Some(stream),
                read_eof: false,
                write_eof: false,
                established: false,
                created: now,
                activity: now,
            },
        );
        self.counters
            .active_tcp_flows
            .store(self.tcp.len(), Ordering::Relaxed);
    }

    fn admit_udp(&mut self, destination: SocketAddr) -> Option<SocketHandle> {
        if let Some(entry) = self.udp.get_mut(&destination) {
            entry.activity = Instant::now();
            return Some(entry.handle);
        }
        if self.udp.len() >= self.config.max_udp_endpoints {
            self.counters
                .dropped_udp_datagrams
                .fetch_add(1, Ordering::Relaxed);
            return None;
        }
        let mut socket = udp::Socket::new(
            udp::PacketBuffer::new(
                vec![udp::PacketMetadata::EMPTY; UDP_PACKET_SLOTS],
                vec![0; self.config.udp_buffer_bytes],
            ),
            udp::PacketBuffer::new(
                vec![udp::PacketMetadata::EMPTY; UDP_PACKET_SLOTS],
                vec![0; self.config.udp_buffer_bytes],
            ),
        );
        socket.bind(destination).ok()?;
        let handle = self.sockets.add(socket);
        self.udp.insert(
            destination,
            UdpEntry {
                handle,
                activity: Instant::now(),
            },
        );
        self.counters
            .active_udp_endpoints
            .store(self.udp.len(), Ordering::Relaxed);
        Some(handle)
    }

    fn poll_stack(&mut self) {
        let timestamp = self.timestamp();
        self.iface.poll_maintenance(timestamp);
        for _ in 0..PACKET_BATCH {
            if self
                .iface
                .poll_ingress_single(timestamp, &mut self.device, &mut self.sockets)
                == PollIngressSingleResult::None
            {
                break;
            }
        }
        self.iface
            .poll_egress(timestamp, &mut self.device, &mut self.sockets);
    }

    fn collect_accepts(&mut self) {
        for (&key, entry) in &mut self.tcp {
            let socket = self.sockets.get_mut::<tcp::Socket>(entry.handle);
            let state = socket.state();
            if state == tcp::State::Established {
                entry.established = true;
            }
            if matches!(state, tcp::State::SynReceived | tcp::State::Established)
                && let Some(stream) = entry.accepted.take()
            {
                // Verify the tuple smoltcp actually accepted, not merely our
                // pre-SYN admission metadata.
                if socket.remote_endpoint().map(SocketAddr::from) != Some(key.0)
                    || socket.local_endpoint().map(SocketAddr::from) != Some(key.1)
                    || self
                        .tcp_tx
                        .try_send(TcpFlow {
                            source: key.0,
                            destination: key.1,
                            stream,
                        })
                        .is_err()
                {
                    socket.abort();
                    self.counters
                        .rejected_tcp_flows
                        .fetch_add(1, Ordering::Relaxed);
                }
            }
        }
    }

    fn collect_udp(&mut self) {
        for (&destination, entry) in &mut self.udp {
            let socket = self.sockets.get_mut::<udp::Socket>(entry.handle);
            for _ in 0..UDP_PACKET_SLOTS {
                let Ok((payload, metadata)) = socket.recv() else {
                    break;
                };
                entry.activity = Instant::now();
                let source = metadata.endpoint.into();
                // recv() preserves datagram boundaries, including empty payloads.
                let datagram = UdpDatagram {
                    source,
                    destination,
                    payload: payload.to_vec(),
                };
                if self.udp_tx.try_send(datagram).is_err() {
                    self.counters
                        .dropped_udp_datagrams
                        .fetch_add(1, Ordering::Relaxed);
                }
            }
        }
    }

    fn emit_ipv6_fragment(&mut self) {
        let Some(fragmenter) = self.ipv6_reply.as_mut() else {
            return;
        };
        let Ok(permit) = self.device.outgoing.try_reserve() else {
            return;
        };
        permit.send(fragmenter.next(self.config.mtu));
        if fragmenter.finished() {
            self.ipv6_reply = None;
        }
    }

    fn reply(&mut self, datagram: UdpDatagram) {
        if datagram.source.is_ipv6() && datagram.payload.len() + 48 > self.config.mtu {
            self.fragment_id = self.fragment_id.wrapping_add(1);
            self.ipv6_reply = UdpFragments::new(datagram, self.fragment_id);
            return;
        }
        let Some(handle) = self.admit_udp(datagram.source) else {
            return;
        };
        let socket = self.sockets.get_mut::<udp::Socket>(handle);
        if socket
            .send_slice(&datagram.payload, datagram.destination)
            .is_err()
        {
            self.counters
                .dropped_udp_datagrams
                .fetch_add(1, Ordering::Relaxed);
        }
    }

    fn poll_bridges(&mut self, cx: &mut Context<'_>) -> Poll<()> {
        let mut progress = false;
        for entry in self.tcp.values_mut() {
            let socket = self.sockets.get_mut::<tcp::Socket>(entry.handle);
            if socket.state() == tcp::State::Closed {
                continue;
            }
            if entry.abort.load(Ordering::Acquire) {
                socket.abort();
                progress = true;
                continue;
            }
            if socket.can_recv() && !entry.write_eof {
                let result = socket.recv(|bytes| {
                    match Pin::new(&mut entry.bridge)
                        .poll_write(cx, &bytes[..bytes.len().min(STREAM_BATCH)])
                    {
                        Poll::Ready(Ok(n)) => (n, Some(Ok(n))),
                        Poll::Ready(Err(err)) => (0, Some(Err(err))),
                        Poll::Pending => (0, None),
                    }
                });
                match result {
                    Ok(Some(Ok(n))) if n > 0 => {
                        progress = true;
                        entry.activity = Instant::now();
                    }
                    Ok(Some(Err(_))) | Ok(Some(Ok(0))) => {
                        socket.abort();
                        progress = true;
                    }
                    _ => {}
                }
            }
            if !entry.read_eof && socket.can_send() {
                let result = socket.send(|bytes| {
                    let len = bytes.len().min(STREAM_BATCH);
                    let mut buffer = ReadBuf::new(&mut bytes[..len]);
                    match Pin::new(&mut entry.bridge).poll_read(cx, &mut buffer) {
                        Poll::Ready(Ok(())) => {
                            let n = buffer.filled().len();
                            (n, Some(Ok(n)))
                        }
                        Poll::Ready(Err(err)) => (0, Some(Err(err))),
                        Poll::Pending => (0, None),
                    }
                });
                match result {
                    Ok(Some(Ok(0))) => {
                        entry.read_eof = true;
                        socket.close();
                        progress = true;
                    }
                    Ok(Some(Ok(_))) => {
                        progress = true;
                        entry.activity = Instant::now();
                    }
                    Ok(Some(Err(_))) => {
                        socket.abort();
                        progress = true;
                    }
                    _ => {}
                }
            }
            // Application FIN becomes EOF only after all preceding bytes have
            // reached the duplex stream. The opposite direction stays alive.
            if !entry.write_eof
                && !socket.may_recv()
                && !matches!(socket.state(), tcp::State::Listen | tcp::State::SynReceived)
            {
                match Pin::new(&mut entry.bridge).poll_shutdown(cx) {
                    Poll::Ready(Ok(())) => {
                        entry.write_eof = true;
                        progress = true;
                    }
                    Poll::Ready(Err(_)) => {
                        entry.write_eof = true;
                        socket.abort();
                        progress = true;
                    }
                    Poll::Pending => {}
                }
            }
        }
        if progress {
            Poll::Ready(())
        } else {
            Poll::Pending
        }
    }

    fn cleanup(&mut self) {
        let now = Instant::now();
        // Closed sockets are removed promptly. Idle-time scanning shares this
        // bounded table walk; no per-connection thread or timer is allocated.
        let check_idle = now.duration_since(self.last_cleanup) >= Duration::from_secs(1);
        if check_idle {
            self.last_cleanup = now;
            self.ipv6_input.expire();
        }
        let mut remove = Vec::new();
        for (&key, entry) in &self.tcp {
            let socket = self.sockets.get_mut::<tcp::Socket>(entry.handle);
            if socket.state() == tcp::State::Closed {
                remove.push(key);
            } else if check_idle
                && ((!entry.established
                    && now.duration_since(entry.created) >= self.config.tcp_handshake_timeout)
                    || now.duration_since(entry.activity) >= self.config.tcp_idle_timeout)
            {
                // Keep the socket one more poll so smoltcp can emit its RST.
                socket.abort();
            }
        }
        for key in remove {
            if let Some(entry) = self.tcp.remove(&key) {
                self.sockets.remove(entry.handle);
            }
        }
        if check_idle {
            self.udp.retain(|_, entry| {
                let keep = now.duration_since(entry.activity) < self.config.udp_idle_timeout;
                if !keep {
                    self.sockets.remove(entry.handle);
                }
                keep
            });
        }
        self.counters
            .active_tcp_flows
            .store(self.tcp.len(), Ordering::Relaxed);
        self.counters
            .active_udp_endpoints
            .store(self.udp.len(), Ordering::Relaxed);
    }
}

impl Drop for Driver {
    fn drop(&mut self) {
        self.counters.active_tcp_flows.store(0, Ordering::Relaxed);
        self.counters
            .active_udp_endpoints
            .store(0, Ordering::Relaxed);
    }
}

//! Read-only physical adapter snapshot for an explicitly requested download.
//! No routes, DNS configuration, proxy policy or global egress lease is changed.
use std::{
    io,
    mem::size_of,
    net::{IpAddr, Ipv4Addr, Ipv6Addr},
};
use windows_sys::Win32::{
    NetworkManagement::IpHelper::{
        FreeMibTable, GAA_FLAG_INCLUDE_GATEWAYS, GetAdaptersAddresses, GetIfEntry2,
        GetIpForwardTable2, IP_ADAPTER_ADDRESSES_LH, MIB_IF_ROW2,
    },
    Networking::WinSock::{
        AF_INET, AF_INET6, AF_UNSPEC, SOCKADDR_IN, SOCKADDR_IN6, SOCKET_ADDRESS,
    },
};

#[derive(Clone)]
pub struct PhysicalInterface {
    pub index: u32,
    pub adapter_id: u64,
    pub source: IpAddr,
    pub metric: u32,
    pub dns: Vec<IpAddr>,
}

/// Active hardware interfaces with a gateway and a preferred source address.
/// Virtual/VPN adapters never enter the candidate set. Family indices are kept
/// separately because Windows does not require IPv4 and IPv6 indices to match.
#[allow(unsafe_code)]
pub fn physical_interfaces() -> io::Result<Vec<PhysicalInterface>> {
    let mut table = std::ptr::null_mut();
    // SAFETY: Windows initializes its owned route-table pointer on success.
    let status = unsafe { GetIpForwardTable2(AF_UNSPEC, &mut table) };
    if status != 0 {
        return Err(io::Error::from_raw_os_error(status as i32));
    }
    // SAFETY: successful API result is a non-null table with NumEntries rows.
    let routes = unsafe {
        std::slice::from_raw_parts((*table).Table.as_ptr(), (*table).NumEntries as usize).to_vec()
    };
    // SAFETY: release exactly the table returned by GetIpForwardTable2.
    unsafe { FreeMibTable(table.cast()) };
    let mut size = 16 * 1024u32;
    for _ in 0..3 {
        if size > 1024 * 1024 {
            return Err(io::Error::other("PhysicalAdapterSnapshotLimit"));
        }
        let mut storage = vec![0u64; (size as usize).div_ceil(size_of::<u64>())];
        let head = storage.as_mut_ptr().cast::<IP_ADAPTER_ADDRESSES_LH>();
        // SAFETY: u64 storage supplies the SDK structure alignment and the byte
        // capacity passed to Windows. All linked pointers are consumed before
        // this owning buffer is dropped; only owned IP values leave this call.
        let status = unsafe {
            GetAdaptersAddresses(
                AF_UNSPEC as u32,
                GAA_FLAG_INCLUDE_GATEWAYS,
                std::ptr::null(),
                head,
                &mut size,
            )
        };
        if status == 111 {
            continue;
        } // ERROR_BUFFER_OVERFLOW: bounded resize.
        if status != 0 {
            return Err(io::Error::from_raw_os_error(status as i32));
        }
        let mut result = Vec::new();
        let mut current = head;
        while !current.is_null() {
            // SAFETY: successful GetAdaptersAddresses owns this linked list in
            // storage, including every subordinate address list used below.
            let adapter = unsafe { &*current };
            current = adapter.Next;
            let mut row = MIB_IF_ROW2 {
                InterfaceLuid: adapter.Luid,
                ..Default::default()
            };
            // SAFETY: initialized writable row identifies this adapter by LUID.
            if unsafe { GetIfEntry2(&mut row) } != 0
                || row.OperStatus != 1
                || row.InterfaceAndOperStatusFlags._bitfield & 1 == 0
            {
                continue;
            }
            let mut dns = Vec::new();
            let mut server = adapter.FirstDnsServerAddress;
            while !server.is_null() {
                let value = unsafe { &*server };
                if let Some(ip) = unsafe { address(value.Address) }
                    && !ip.is_unspecified()
                    && !ip.is_loopback()
                    && !dns.contains(&ip)
                {
                    dns.push(ip);
                }
                server = value.Next;
            }
            let mut gateways = Vec::new();
            let mut gateway = adapter.FirstGatewayAddress;
            while !gateway.is_null() {
                let value = unsafe { &*gateway };
                if let Some(ip) = unsafe { address(value.Address) }
                    && !ip.is_unspecified()
                {
                    gateways.push(ip);
                }
                gateway = value.Next;
            }
            let mut unicast = adapter.FirstUnicastAddress;
            while !unicast.is_null() {
                let value = unsafe { &*unicast };
                unicast = value.Next;
                if value.DadState != 4 {
                    continue;
                } // IpDadStatePreferred.
                let Some(source) = (unsafe { address(value.Address) }) else {
                    continue;
                };
                if source.is_loopback()
                    || source.is_unspecified()
                    || !gateways.iter().any(|ip| ip.is_ipv6() == source.is_ipv6())
                {
                    continue;
                }
                if matches!(source, IpAddr::V6(ip) if ip.is_unicast_link_local()) {
                    continue;
                }
                let family = if source.is_ipv6() { AF_INET6 } else { AF_INET };
                let adapter_id = unsafe { adapter.Luid.Value };
                let Some(route_metric)=routes.iter().filter(|route|
                    unsafe { route.InterfaceLuid.Value } == adapter_id
                    && route.DestinationPrefix.PrefixLength == 0
                    && unsafe { route.DestinationPrefix.Prefix.si_family } == family
                    && !route.Loopback && route.ValidLifetime>0).map(|route|route.Metric).min() else { continue; };
                result.push(PhysicalInterface {
                    index: if source.is_ipv6() {
                        adapter.Ipv6IfIndex
                    } else {
                        row.InterfaceIndex
                    },
                    adapter_id,
                    source,
                    metric: route_metric.saturating_add(if source.is_ipv6() {
                        adapter.Ipv6Metric
                    } else {
                        adapter.Ipv4Metric
                    }),
                    dns: dns.clone(),
                });
            }
        }
        result.sort_by_key(|entry| entry.metric);
        if result.is_empty() {
            return Err(io::Error::other("PhysicalNetworkUnavailable"));
        }
        return Ok(result);
    }
    Err(io::Error::other("PhysicalAdapterSnapshotChanged"))
}

#[allow(unsafe_code)]
unsafe fn address(value: SOCKET_ADDRESS) -> Option<IpAddr> {
    if value.lpSockaddr.is_null() {
        return None;
    }
    // SAFETY: caller supplies a socket-address entry in a successful SDK list;
    // verify its family and length before reading the corresponding structure.
    match unsafe { (*value.lpSockaddr).sa_family } {
        AF_INET if value.iSockaddrLength as usize >= size_of::<SOCKADDR_IN>() => {
            let addr = unsafe { &*value.lpSockaddr.cast::<SOCKADDR_IN>() };
            Some(Ipv4Addr::from(unsafe { addr.sin_addr.S_un.S_addr }.to_ne_bytes()).into())
        }
        AF_INET6 if value.iSockaddrLength as usize >= size_of::<SOCKADDR_IN6>() => {
            let addr = unsafe { &*value.lpSockaddr.cast::<SOCKADDR_IN6>() };
            Some(Ipv6Addr::from(unsafe { addr.sin6_addr.u.Byte }).into())
        }
        _ => None,
    }
}

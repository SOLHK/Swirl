//! Moves packets between a device and the userspace stack. The device may be
//! Wintun on Windows or an in-memory stand-in in tests. Neither path dials a
//! second local proxy.
use crate::stack::Engine;

pub trait PacketIo {
    fn recv_packet(&mut self) -> Result<Option<Vec<u8>>, &'static str>;
    fn send_packet(&mut self, packet: &[u8]) -> Result<(), &'static str>;
}

/// Pull a bounded burst into the engine, then write whatever the stack emits.
pub fn pump(
    engine: &mut Engine,
    device: &mut dyn PacketIo,
    max_in: usize,
) -> Result<usize, &'static str> {
    let mut moved = 0;
    for _ in 0..max_in {
        match device.recv_packet()? {
            Some(packet) => {
                engine.push(&packet)?;
                moved += 1;
            }
            None => break,
        }
    }
    for packet in engine.poll() {
        device.send_packet(&packet)?;
        moved += 1;
    }
    Ok(moved)
}

#[cfg(test)]
mod tests {
    use std::{collections::VecDeque, time::Duration};

    use super::*;
    use crate::{
        Dispatch, FlowMeta, LoopGuard, TableDns, VirtualClient,
        dispatch::{Decision, Pipe},
        stack::Engine,
    };

    struct Memory {
        inbound: VecDeque<Vec<u8>>,
        outbound: Vec<Vec<u8>>,
    }

    impl PacketIo for Memory {
        fn recv_packet(&mut self) -> Result<Option<Vec<u8>>, &'static str> {
            Ok(self.inbound.pop_front())
        }
        fn send_packet(&mut self, packet: &[u8]) -> Result<(), &'static str> {
            self.outbound.push(packet.to_vec());
            Ok(())
        }
    }

    struct Idle;

    impl Dispatch for Idle {
        fn open_tcp(&mut self, _: &FlowMeta) -> Result<(Decision, Box<dyn Pipe>), &'static str> {
            Err("Idle")
        }
        fn open_udp(&mut self, _: &FlowMeta) -> Result<Box<dyn crate::UdpPipe>, &'static str> {
            Err("Idle")
        }
    }

    #[test]
    fn pump_returns_the_handshake_without_a_nic() {
        let (dns, association) = TableDns::fake(Duration::from_secs(30));
        let mut engine = Engine::new(
            Box::new(Idle),
            Box::new(dns),
            association,
            LoopGuard::new([]),
            true,
        )
        .unwrap();
        let mut client = VirtualClient::connect(
            "10.0.0.9:44000".parse().unwrap(),
            "198.51.100.10:443".parse().unwrap(),
        )
        .unwrap();
        let mut device = Memory {
            inbound: client.poll().into(),
            outbound: Vec::new(),
        };
        let moved = pump(&mut engine, &mut device, 8).unwrap();
        assert!(moved >= 1);
        assert!(!device.outbound.is_empty());
    }
}

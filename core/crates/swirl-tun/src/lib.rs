//! Native TUN session adapter. Wintun and smoltcp stop at packets and TCP;
//! DNS, rules and proxy protocols stay in the existing Swirl crates.
mod command;
mod device;
mod dispatch;
mod dns_flow;
mod guard;
mod link;
pub mod packet;
mod plan;
mod recovery;
mod service;
mod stack;

pub use command::{Control, command};
pub use device::{PacketIo, pump};
pub use dispatch::{
    Action, ChannelPipe, ChannelUdp, Chunk, Decision, Dispatch, FlowMeta, Pipe, Pull, Push,
    UdpPipe, UdpReply, decide_flow,
};
pub use dns_flow::{DnsAnswer, DnsReply, TableDns};
pub use guard::{LoopGuard, LoopVerdict};
pub use stack::{Engine, Stats, VirtualClient};
pub use swirl_wintun::{Session, open_session, probe};

#[cfg(test)]
#[path = "engine_tests.rs"]
mod engine_tests;

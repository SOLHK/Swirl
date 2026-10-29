//! One decision per flow. Packet pumps reuse it instead of matching rules again.
use std::{
    net::SocketAddr,
    sync::mpsc::{Receiver, SyncSender, TryRecvError, TrySendError},
};

use swirl_subscription::v2::{DIRECT_NODE_ID, REJECT_NODE_ID, Target};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FlowMeta {
    pub source: SocketAddr,
    pub destination: SocketAddr,
    pub domain: Option<String>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Action {
    Direct,
    Proxy,
    Reject,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Decision {
    pub action: Action,
    pub rule_id: String,
    pub node_id: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Chunk {
    Data(Vec<u8>),
    Shutdown,
}

#[derive(Debug)]
pub enum Push {
    Queued,
    Full(Chunk),
    Closed,
}

#[derive(Debug)]
pub enum Pull {
    Empty,
    Chunk(Chunk),
    Closed,
}

pub trait Pipe: Send {
    fn push_upstream(&mut self, chunk: Chunk) -> Push;
    fn pull_downstream(&mut self) -> Pull;
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UdpReply {
    pub source: SocketAddr,
    pub payload: Vec<u8>,
}

pub trait UdpPipe: Send {
    fn push(&mut self, payload: &[u8]) -> bool;
    fn pull(&mut self) -> Option<UdpReply>;
    fn decision(&self) -> &Decision;
}

pub trait Dispatch: Send {
    fn open_tcp(&mut self, meta: &FlowMeta) -> Result<(Decision, Box<dyn Pipe>), &'static str>;
    fn open_udp(&mut self, meta: &FlowMeta) -> Result<Box<dyn UdpPipe>, &'static str>;
}

/// Run the existing V2 selector once. Group membership stays inside Core;
/// this preview refuses to guess a member or to turn a proxy target into DIRECT.
pub fn decide_flow(
    policy: &swirl_subscription::v2::PolicyDocument,
    meta: &FlowMeta,
) -> Result<Decision, &'static str> {
    let mut policy = policy.clone();
    policy.normalize()?;
    if meta.destination.port() == 0 {
        return Err("InvalidTarget");
    }
    let host = meta
        .domain
        .clone()
        .unwrap_or_else(|| meta.destination.ip().to_string());
    let bundled = if policy.mode == swirl_subscription::v2::Mode::Rule {
        Some(swirl_routing::shared_bundled_rules()?)
    } else {
        None
    };
    let china = bundled
        .as_ref()
        .map(|(domains, ips)| (domains.as_ref(), ips.as_ref()));
    let selected = swirl_routing::v2::select(
        &policy,
        &host,
        meta.destination.port(),
        meta.source.ip(),
        Some(meta.destination.ip()),
        true,
        china,
    )?;
    if selected.resolution.is_some() {
        return Err("TunResolutionUnavailable");
    }
    let (action, node_id) = match selected.target {
        Target::Direct {} => (Action::Direct, DIRECT_NODE_ID.to_owned()),
        Target::Reject {} => (Action::Reject, REJECT_NODE_ID.to_owned()),
        Target::Node { id } => (Action::Proxy, id),
        Target::Group { .. } => return Err("TunGroupRequiresCore"),
        Target::Unconfigured {} => return Err("UnconfiguredTarget"),
    };
    Ok(Decision {
        action,
        rule_id: selected.rule_id,
        node_id,
    })
}

pub struct ChannelPipe {
    upload: SyncSender<Chunk>,
    download: Receiver<Chunk>,
}

impl ChannelPipe {
    pub fn pair(bound: usize) -> (Self, SyncSender<Chunk>, Receiver<Chunk>) {
        let (upload, upload_rx) = std::sync::mpsc::sync_channel(bound);
        let (download_tx, download) = std::sync::mpsc::sync_channel(bound);
        (Self { upload, download }, download_tx, upload_rx)
    }
}

impl Pipe for ChannelPipe {
    fn push_upstream(&mut self, chunk: Chunk) -> Push {
        match self.upload.try_send(chunk) {
            Ok(()) => Push::Queued,
            Err(TrySendError::Full(chunk)) => Push::Full(chunk),
            Err(TrySendError::Disconnected(_)) => Push::Closed,
        }
    }
    fn pull_downstream(&mut self) -> Pull {
        match self.download.try_recv() {
            Ok(chunk) => Pull::Chunk(chunk),
            Err(TryRecvError::Empty) => Pull::Empty,
            Err(TryRecvError::Disconnected) => Pull::Closed,
        }
    }
}

pub struct ChannelUdp {
    decision: Decision,
    upload: SyncSender<Vec<u8>>,
    download: Receiver<UdpReply>,
}

impl ChannelUdp {
    pub fn pair(
        decision: Decision,
        bound: usize,
    ) -> (Self, SyncSender<UdpReply>, Receiver<Vec<u8>>) {
        let (upload, upload_rx) = std::sync::mpsc::sync_channel(bound);
        let (download_tx, download) = std::sync::mpsc::sync_channel(bound);
        (
            Self {
                decision,
                upload,
                download,
            },
            download_tx,
            upload_rx,
        )
    }
}

impl UdpPipe for ChannelUdp {
    fn push(&mut self, payload: &[u8]) -> bool {
        self.upload.try_send(payload.to_vec()).is_ok()
    }
    fn pull(&mut self) -> Option<UdpReply> {
        self.download.try_recv().ok()
    }
    fn decision(&self) -> &Decision {
        &self.decision
    }
}

#[cfg(test)]
mod tests {
    use std::net::SocketAddr;

    use swirl_subscription::v2::{
        ClassificationDns, DEFAULT_POLICY_ID, DefaultPolicy, DomainMatch, Mode, PolicyDocument,
        ServicePolicy, Target,
    };

    use super::{Action, FlowMeta, decide_flow};

    fn document(mode: Mode, target: Target) -> PolicyDocument {
        PolicyDocument {
            schema: 2,
            mode,
            default_policy: DefaultPolicy {
                id: DEFAULT_POLICY_ID.into(),
                target,
            },
            service_policies: Vec::new(),
            groups: Vec::new(),
            explicit_direct_rules: Vec::new(),
            custom_rules: Vec::new(),
            missing_targets: Vec::new(),
            classification_dns: ClassificationDns::Disabled,
        }
    }

    fn flow(host: Option<&str>, address: &str) -> FlowMeta {
        FlowMeta {
            source: "10.0.0.2:40000".parse().unwrap(),
            destination: address.parse::<SocketAddr>().unwrap(),
            domain: host.map(str::to_owned),
        }
    }

    #[test]
    fn tun_decisions_match_the_v2_selector_and_do_not_guess_groups() {
        let node = Target::Node {
            id: "10000000-0000-4000-8000-000000000009".into(),
        };
        let global = document(Mode::Global, node.clone());
        let proxied = decide_flow(&global, &flow(Some("example.com"), "1.2.3.4:443")).unwrap();
        assert_eq!(proxied.action, Action::Proxy);
        assert_eq!(proxied.node_id, "10000000-0000-4000-8000-000000000009");
        let local = decide_flow(&global, &flow(None, "127.0.0.1:80")).unwrap();
        assert_eq!(
            (local.action, local.rule_id.as_str()),
            (Action::Direct, "builtin:local-v1")
        );
        let direct = decide_flow(
            &document(Mode::Direct, node.clone()),
            &flow(Some("example.com"), "1.2.3.4:443"),
        )
        .unwrap();
        assert_eq!(direct.action, Action::Direct);
        let rejected = decide_flow(
            &document(Mode::Global, Target::Reject {}),
            &flow(None, "203.0.113.9:443"),
        )
        .unwrap();
        assert_eq!(rejected.action, Action::Reject);
        assert_eq!(
            decide_flow(&global, &flow(None, "1.2.3.4:0")),
            Err("InvalidTarget")
        );
        let mut rules = document(Mode::Rule, Target::Direct {});
        rules.service_policies.push(ServicePolicy {
            id: "service:example".into(),
            name: "Example".into(),
            enabled: true,
            priority: 1,
            domains: vec![DomainMatch::Domain {
                value: "example.com".into(),
            }],
            target: node,
            catalog_key: None,
            catalog_version: None,
        });
        let service = decide_flow(&rules, &flow(Some("example.com"), "1.2.3.4:443")).unwrap();
        assert_eq!(service.rule_id, "service:example");
        assert_eq!(service.action, Action::Proxy);
        let grouped = document(
            Mode::Global,
            Target::Group {
                id: "20000000-0000-4000-8000-000000000001".into(),
            },
        );
        assert_eq!(
            decide_flow(&grouped, &flow(Some("example.com"), "1.2.3.4:443")),
            Err("TunGroupRequiresCore")
        );
    }
}

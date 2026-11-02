//! Lifecycle around the in-memory network store. Starting does not touch the host.
use std::net::IpAddr;

use crate::{
    link::{LinkEvent, LinkMachine, LinkPhase},
    plan::{self, PlannedCommand},
    recovery::{MemoryStore, NetworkSnapshot, RestorePhase, RestoreTransaction},
};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Phase {
    Idle,
    Running,
    Stopped,
}

pub struct Controller {
    phase: Phase,
    link: LinkMachine,
    journal: Option<RestoreTransaction>,
    store: MemoryStore,
    commands: Vec<PlannedCommand>,
}

impl Controller {
    pub fn new(store: MemoryStore, interface_id: impl Into<String>) -> Self {
        let interface_id = interface_id.into();
        Self {
            phase: Phase::Idle,
            link: LinkMachine::new("unset", interface_id),
            journal: None,
            store,
            commands: Vec::new(),
        }
    }

    pub fn phase(&self) -> Phase {
        self.phase
    }

    pub fn packets_allowed(&self) -> bool {
        self.phase == Phase::Running && self.link.phase() == LinkPhase::Active
    }

    pub fn commands(&self) -> &[PlannedCommand] {
        &self.commands
    }

    pub fn store(&self) -> &NetworkSnapshot {
        self.store.read()
    }

    pub fn start(
        &mut self,
        owner: &str,
        physical: &str,
        proxies: &[IpAddr],
    ) -> Result<(), &'static str> {
        if self.phase == Phase::Running {
            return Err("TunAlreadyRunning");
        }
        let before = self.store.read().clone();
        let mut journal = RestoreTransaction::begin(owner, before)?;
        let mut desired = self.store.read().clone();
        desired.owner = owner.to_owned();
        desired.generation = desired.generation.saturating_add(1);
        desired
            .adapters
            .retain(|name| !name.eq_ignore_ascii_case("swirl"));
        desired.adapters.push("Swirl".into());
        if let Some(dns) = desired
            .dns
            .iter_mut()
            .find(|dns| dns.interface_id == "Swirl")
        {
            dns.servers = vec!["198.18.0.2".into(), "fd53:5749:524c::2".into()];
        } else {
            desired.dns.push(crate::recovery::DnsRecord {
                interface_id: "Swirl".into(),
                servers: vec!["198.18.0.2".into(), "fd53:5749:524c::2".into()],
            });
        }
        self.commands = plan::plan_activation(owner, physical, proxies)?;
        journal.apply(&mut self.store, desired)?;
        self.link = LinkMachine::new(owner, physical);
        self.journal = Some(journal);
        self.phase = Phase::Running;
        Ok(())
    }

    pub fn on_link(&mut self, event: LinkEvent) -> Result<LinkPhase, &'static str> {
        let owner = self.store.read().owner.clone();
        self.link.on_event(event, &owner)
    }

    pub fn journal_owner(&self) -> Option<&str> {
        self.journal.as_ref().map(RestoreTransaction::owner)
    }

    pub fn saved_generation(&self) -> Option<u64> {
        self.journal
            .as_ref()
            .map(|journal| journal.before().generation)
    }

    pub fn stop(&mut self) -> Result<(), &'static str> {
        if let Some(journal) = self.journal.as_ref()
            && journal.phase() == RestorePhase::Applied
        {
            crate::recovery::reconcile(&self.store, journal)?;
        }
        let Some(journal) = self.journal.as_mut() else {
            self.phase = Phase::Stopped;
            return Ok(());
        };
        journal.restore(&mut self.store)?;
        self.phase = Phase::Stopped;
        self.commands.clear();
        Ok(())
    }

    pub fn link_interface(&self) -> &str {
        self.link.interface_id()
    }

    pub fn journal_phase(&self) -> Option<RestorePhase> {
        self.journal.as_ref().map(RestoreTransaction::phase)
    }
}

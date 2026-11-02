//! Owner-checked snapshot of routes and DNS. Applying and restoring are
//! explicit; a foreign owner never receives the previous snapshot.
use serde_json::{Value, json};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RouteRecord {
    pub destination: String,
    pub gateway: String,
    pub interface_id: String,
    pub metric: u32,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DnsRecord {
    pub interface_id: String,
    pub servers: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NetworkSnapshot {
    pub owner: String,
    pub generation: u64,
    pub routes_v4: Vec<RouteRecord>,
    pub routes_v6: Vec<RouteRecord>,
    pub dns: Vec<DnsRecord>,
    pub adapters: Vec<String>,
}

impl NetworkSnapshot {
    pub fn system() -> Self {
        Self {
            owner: "system".into(),
            generation: 1,
            routes_v4: vec![RouteRecord {
                destination: "0.0.0.0/0".into(),
                gateway: "192.0.2.1".into(),
                interface_id: "physical".into(),
                metric: 25,
            }],
            routes_v6: vec![RouteRecord {
                destination: "::/0".into(),
                gateway: "2001:db8::1".into(),
                interface_id: "physical".into(),
                metric: 25,
            }],
            dns: vec![DnsRecord {
                interface_id: "physical".into(),
                servers: vec!["192.0.2.53".into()],
            }],
            adapters: vec!["physical".into()],
        }
    }

    pub fn to_json(&self) -> Value {
        json!({
            "owner": self.owner,
            "generation": self.generation,
            "routes_v4": self.routes_v4.len(),
            "routes_v6": self.routes_v6.len(),
            "dns": self.dns.len(),
            "adapters": self.adapters,
        })
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RestorePhase {
    Saved,
    Applied,
    Restored,
    Failed,
}

#[derive(Clone, Debug)]
pub struct RestoreTransaction {
    owner: String,
    before: NetworkSnapshot,
    phase: RestorePhase,
}

impl RestoreTransaction {
    pub fn begin(owner: &str, before: NetworkSnapshot) -> Result<Self, &'static str> {
        validate_owner(owner)?;
        Ok(Self {
            owner: owner.to_owned(),
            before,
            phase: RestorePhase::Saved,
        })
    }

    pub fn owner(&self) -> &str {
        &self.owner
    }

    pub fn phase(&self) -> RestorePhase {
        self.phase
    }

    pub fn before(&self) -> &NetworkSnapshot {
        &self.before
    }

    pub fn apply(
        &mut self,
        store: &mut MemoryStore,
        desired: NetworkSnapshot,
    ) -> Result<(), &'static str> {
        if self.phase != RestorePhase::Saved {
            return Err("RestorePhase");
        }
        if desired.owner != self.owner {
            return Err("RestoreOwnerMismatch");
        }
        store.write(desired)?;
        self.phase = RestorePhase::Applied;
        Ok(())
    }

    pub fn restore(&mut self, store: &mut MemoryStore) -> Result<(), &'static str> {
        if !matches!(self.phase, RestorePhase::Applied | RestorePhase::Failed) {
            return Err("RestorePhase");
        }
        if store.snapshot.owner != self.owner {
            self.phase = RestorePhase::Failed;
            return Err("RestoreOwnerMismatch");
        }
        store.snapshot = self.before.clone();
        self.phase = RestorePhase::Restored;
        Ok(())
    }
}

/// Returns the saved snapshot when this owner still holds the store.
/// A different owner produces an error and the caller must not write.
pub fn reconcile(
    store: &MemoryStore,
    journal: &RestoreTransaction,
) -> Result<NetworkSnapshot, &'static str> {
    if journal.phase != RestorePhase::Applied {
        return Err("RestorePhase");
    }
    if store.snapshot.owner != journal.owner {
        return Err("RestoreForeignAdapter");
    }
    Ok(journal.before.clone())
}

#[derive(Clone, Debug)]
pub struct MemoryStore {
    snapshot: NetworkSnapshot,
}

impl MemoryStore {
    pub fn new(snapshot: NetworkSnapshot) -> Self {
        Self { snapshot }
    }

    pub fn read(&self) -> &NetworkSnapshot {
        &self.snapshot
    }

    fn write(&mut self, snapshot: NetworkSnapshot) -> Result<(), &'static str> {
        validate_owner(&snapshot.owner)?;
        self.snapshot = snapshot;
        Ok(())
    }
}

fn validate_owner(owner: &str) -> Result<(), &'static str> {
    if owner.is_empty()
        || owner.len() > 64
        || owner.chars().any(|c| c.is_whitespace() || c.is_control())
    {
        Err("RestoreOwner")
    } else {
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn restore_requires_the_same_owner_and_foreign_state_is_left_alone() {
        let before = NetworkSnapshot::system();
        let mut store = MemoryStore::new(before.clone());
        let mut journal = RestoreTransaction::begin("tun-owner-1", before.clone()).unwrap();
        let mut desired = before.clone();
        desired.owner = "tun-owner-1".into();
        desired.generation = 2;
        desired.dns[0].servers = vec!["198.18.0.2".into()];
        journal.apply(&mut store, desired).unwrap();
        assert_eq!(store.read().dns[0].servers, vec!["198.18.0.2".to_string()]);
        let saved = reconcile(&store, &journal).unwrap();
        assert_eq!(saved.owner, "system");
        assert_eq!(journal.owner(), "tun-owner-1");
        assert_eq!(journal.before().owner, "system");
        store.snapshot.owner = "other-vpn".into();
        assert_eq!(reconcile(&store, &journal), Err("RestoreForeignAdapter"));
        assert_eq!(journal.restore(&mut store), Err("RestoreOwnerMismatch"));
        assert_eq!(store.read().owner, "other-vpn");
        store.snapshot.owner = "tun-owner-1".into();
        journal.phase = RestorePhase::Applied;
        journal.restore(&mut store).unwrap();
        assert_eq!(store.read(), &before);
        assert_eq!(journal.phase(), RestorePhase::Restored);
    }
}

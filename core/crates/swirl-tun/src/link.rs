//! Pause packet intake across link loss and resume only for the same owner.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LinkEvent {
    Down,
    Up,
    Sleep,
    Resume,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LinkPhase {
    Active,
    Paused,
    Failed,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LinkMachine {
    phase: LinkPhase,
    owner: String,
    interface_id: String,
}

impl LinkMachine {
    pub fn new(owner: impl Into<String>, interface_id: impl Into<String>) -> Self {
        Self {
            phase: LinkPhase::Active,
            owner: owner.into(),
            interface_id: interface_id.into(),
        }
    }

    pub fn phase(&self) -> LinkPhase {
        self.phase
    }

    pub fn interface_id(&self) -> &str {
        &self.interface_id
    }

    pub fn on_event(
        &mut self,
        event: LinkEvent,
        store_owner: &str,
    ) -> Result<LinkPhase, &'static str> {
        match event {
            LinkEvent::Down | LinkEvent::Sleep => {
                if self.phase == LinkPhase::Failed {
                    return Err("LinkFailed");
                }
                self.phase = LinkPhase::Paused;
                Ok(self.phase)
            }
            LinkEvent::Up | LinkEvent::Resume => {
                if store_owner != self.owner {
                    self.phase = LinkPhase::Failed;
                    return Err("RestoreOwnerMismatch");
                }
                self.phase = LinkPhase::Active;
                Ok(self.phase)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sleep_pauses_and_only_the_owner_may_resume() {
        let mut link = LinkMachine::new("tun-owner-1", "ethernet");
        assert_eq!(
            link.on_event(LinkEvent::Sleep, "tun-owner-1"),
            Ok(LinkPhase::Paused)
        );
        assert_eq!(
            link.on_event(LinkEvent::Down, "tun-owner-1"),
            Ok(LinkPhase::Paused)
        );
        assert_eq!(
            link.on_event(LinkEvent::Resume, "other-vpn"),
            Err("RestoreOwnerMismatch")
        );
        assert_eq!(link.phase(), LinkPhase::Failed);
        assert_eq!(
            link.on_event(LinkEvent::Up, "tun-owner-1"),
            Ok(LinkPhase::Active)
        );
    }
}

use smoltcp::{
    phy::{Device, DeviceCapabilities, Medium, RxToken, TxToken},
    time::Instant,
};
use std::collections::VecDeque;
use tokio::sync::mpsc;

pub(crate) struct PacketDevice {
    pub incoming: VecDeque<Vec<u8>>,
    pub outgoing: mpsc::Sender<Vec<u8>>,
    mtu: usize,
}

impl PacketDevice {
    pub fn new(outgoing: mpsc::Sender<Vec<u8>>, mtu: usize) -> Self {
        Self {
            incoming: VecDeque::new(),
            outgoing,
            mtu,
        }
    }
}

pub(crate) struct ReceiveToken(Vec<u8>);
pub(crate) struct TransmitToken(mpsc::OwnedPermit<Vec<u8>>);

impl RxToken for ReceiveToken {
    fn consume<R, F>(self, f: F) -> R
    where
        F: FnOnce(&[u8]) -> R,
    {
        f(&self.0)
    }
}

impl TxToken for TransmitToken {
    fn consume<R, F>(self, len: usize, f: F) -> R
    where
        F: FnOnce(&mut [u8]) -> R,
    {
        let mut bytes = vec![0; len];
        let result = f(&mut bytes);
        self.0.send(bytes);
        result
    }
}

impl Device for PacketDevice {
    type RxToken<'a> = ReceiveToken;
    type TxToken<'a> = TransmitToken;

    fn receive(&mut self, _timestamp: Instant) -> Option<(Self::RxToken<'_>, Self::TxToken<'_>)> {
        if self.incoming.is_empty() {
            return None;
        }
        let permit = self.outgoing.clone().try_reserve_owned().ok()?;
        let packet = self.incoming.pop_front()?;
        Some((ReceiveToken(packet), TransmitToken(permit)))
    }

    fn transmit(&mut self, _timestamp: Instant) -> Option<Self::TxToken<'_>> {
        self.outgoing
            .clone()
            .try_reserve_owned()
            .ok()
            .map(TransmitToken)
    }

    fn capabilities(&self) -> DeviceCapabilities {
        let mut capabilities = DeviceCapabilities::default();
        capabilities.medium = Medium::Ip;
        capabilities.max_transmission_unit = self.mtu;
        capabilities
    }
}

use std::{io, sync::mpsc, thread, time::Duration};

/// Keep a stalled parent pipe from blocking the lifecycle thread indefinitely.
/// There is one writer and at most one queued response; timeout poisons this
/// connection. The caller owns its cleanup and recovery before process exit.
pub(crate) struct BoundedOutput {
    pending: mpsc::SyncSender<serde_json::Value>,
    completed: mpsc::Receiver<io::Result<()>>,
    poisoned: bool,
}

impl BoundedOutput {
    pub(crate) fn new(
        mut write: impl FnMut(&serde_json::Value) -> io::Result<()> + Send + 'static,
    ) -> io::Result<Self> {
        let (pending, input) = mpsc::sync_channel(1);
        let (finished, completed) = mpsc::sync_channel(1);
        thread::Builder::new()
            .name("swirl-helper-response".into())
            .spawn(move || {
                while let Ok(value) = input.recv() {
                    let result = write(&value);
                    let failed = result.is_err();
                    if finished.send(result).is_err() || failed {
                        break;
                    }
                }
            })?;
        Ok(Self {
            pending,
            completed,
            poisoned: false,
        })
    }

    pub(crate) fn write(&mut self, value: serde_json::Value, deadline: Duration) -> io::Result<()> {
        if self.poisoned {
            return Err(io::Error::other("TunHelperOutputPoisoned"));
        }
        let result = (|| {
            self.pending
                .try_send(value)
                .map_err(|_| io::Error::other("TunHelperOutputClosed"))?;
            self.completed
                .recv_timeout(deadline)
                .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "TunHelperOutputBlocked"))?
        })();
        self.poisoned = result.is_err();
        result
    }
}

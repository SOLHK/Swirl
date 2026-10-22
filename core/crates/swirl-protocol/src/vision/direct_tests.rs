//! State/ownership regressions only. This synthetic owner is not TLS or Xray
//! interoperability evidence; the product-path peer tests supply that separately.
use super::*;
use std::{
    future::poll_fn,
    io::Cursor,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, AtomicUsize, Ordering},
    },
    time::Duration,
};
use tokio::io::{AsyncReadExt, AsyncWriteExt};

const UUID: [u8; UUID_LEN] = [0x53; UUID_LEN];

#[derive(Default)]
struct Observation {
    read_switches: usize,
    write_switches: usize,
    writes: Vec<(bool, Vec<u8>)>,
    shutdowns: usize,
}

struct Owner {
    outer: Cursor<Vec<u8>>,
    residual: Vec<u8>,
    raw: Cursor<Vec<u8>>,
    read_raw: bool,
    write_raw: bool,
    chop: usize,
    blocked_flush: Arc<AtomicBool>,
    observation: Arc<Mutex<Observation>>,
    drops: Arc<AtomicUsize>,
}

impl Drop for Owner {
    fn drop(&mut self) {
        self.drops.fetch_add(1, Ordering::SeqCst);
    }
}

impl AsyncRead for Owner {
    fn poll_read(
        self: Pin<&mut Self>,
        _: &mut Context<'_>,
        out: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        let source = if this.read_raw {
            &mut this.raw
        } else {
            &mut this.outer
        };
        let start = source.position() as usize;
        if start == source.get_ref().len() && !this.read_raw {
            return Poll::Pending;
        }
        let count = out
            .remaining()
            .min(source.get_ref().len() - start)
            .min(this.chop);
        out.put_slice(&source.get_ref()[start..start + count]);
        source.set_position((start + count) as u64);
        Poll::Ready(Ok(()))
    }
}

impl AsyncWrite for Owner {
    fn poll_write(
        self: Pin<&mut Self>,
        _: &mut Context<'_>,
        bytes: &[u8],
    ) -> Poll<io::Result<usize>> {
        let count = bytes.len().min(self.chop);
        self.observation
            .lock()
            .unwrap()
            .writes
            .push((self.write_raw, bytes[..count].to_vec()));
        Poll::Ready(Ok(count))
    }

    fn poll_flush(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<io::Result<()>> {
        if self.blocked_flush.load(Ordering::SeqCst) {
            Poll::Pending
        } else {
            Poll::Ready(Ok(()))
        }
    }

    fn poll_shutdown(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<io::Result<()>> {
        self.observation.lock().unwrap().shutdowns += 1;
        Poll::Ready(Ok(()))
    }
}

fn record(kind: u8, body: &[u8]) -> Vec<u8> {
    [
        &[kind, 3, 3],
        (body.len() as u16).to_be_bytes().as_slice(),
        body,
    ]
    .concat()
}

fn hello(server: bool) -> Vec<u8> {
    let mut body = vec![3, 3];
    body.extend([0x61; 32]);
    body.push(0);
    if !server {
        body.extend([0, 2]);
    }
    body.extend([0x13, 1]);
    body.extend(if server { &[0][..] } else { &[1, 0][..] });
    body.extend(if server {
        &[0, 6, 0, 43, 0, 2, 3, 4][..]
    } else {
        &[0, 7, 0, 43, 0, 3, 2, 3, 4][..]
    });
    let mut message = vec![if server { 2 } else { 1 }];
    message.extend(&(body.len() as u32).to_be_bytes()[1..]);
    message.extend(body);
    record(22, &message)
}

fn peer_frames(command: Command, payload: &[u8], padding: &[u8], tail: &[u8]) -> Vec<u8> {
    let mut encoder = Encoder::new(UUID);
    let mut wire = encoder.frame(Command::Continue, &hello(true), &[]).unwrap();
    wire.extend(encoder.frame(command, payload, padding).unwrap());
    wire.extend(tail);
    wire
}

fn stream(outer: Vec<u8>, residual: Vec<u8>, raw: Vec<u8>, chop: usize) -> Stream<Owner> {
    let owner = Owner {
        outer: Cursor::new(outer),
        residual,
        raw: Cursor::new(raw),
        read_raw: false,
        write_raw: false,
        chop,
        blocked_flush: Arc::new(AtomicBool::new(false)),
        observation: Arc::new(Mutex::new(Observation::default())),
        drops: Arc::new(AtomicUsize::new(0)),
    };
    let mut stream = Stream::new(owner, UUID, Role::Client);
    stream.handoff = Some(Handoff {
        read: |owner| {
            assert!(!owner.read_raw);
            let offset = owner.outer.position() as usize;
            let mut residual = owner.outer.get_ref()[offset..].to_vec();
            owner.outer.set_position(owner.outer.get_ref().len() as u64);
            residual.append(&mut owner.residual);
            owner.read_raw = true;
            owner.observation.lock().unwrap().read_switches += 1;
            Ok(residual)
        },
        write: |owner, cx| {
            ready!(Pin::new(&mut *owner).poll_flush(cx))?;
            assert!(!owner.write_raw);
            owner.write_raw = true;
            owner.observation.lock().unwrap().write_switches += 1;
            Poll::Ready(Ok(()))
        },
    });
    stream
}

async fn hellos(stream: &mut Stream<Owner>) {
    stream.write_all(&hello(false)).await.unwrap();
    stream.flush().await.unwrap();
    let mut server = vec![0; hello(true).len()];
    stream.read_exact(&mut server).await.unwrap();
    assert_eq!(server, hello(true));
    assert!(matches!(
        stream.inspection().eligibility(),
        tls::Eligibility::Candidate { .. }
    ));
}

#[tokio::test]
async fn direct_read_keeps_terminal_tail_engine_residual_and_raw_bytes_in_order() {
    let terminal = record(23, &[0x47; 511]);
    let tail = vec![0x17; 12000];
    let residual = b"engine-authenticated-residual".to_vec();
    let raw = b"raw-socket-tail".to_vec();
    for chop in [1, 31, 8192] {
        let mut stream = stream(
            peer_frames(Command::DirectRequested, &terminal, &[0x21; 121], &tail),
            residual.clone(),
            raw.clone(),
            chop,
        );
        let observation = stream.inner.as_ref().unwrap().observation.clone();
        let drops = stream.inner.as_ref().unwrap().drops.clone();
        hellos(&mut stream).await;
        let mut output = Vec::new();
        stream.read_to_end(&mut output).await.unwrap();
        assert_eq!(
            output,
            [
                terminal.clone(),
                tail.clone(),
                residual.clone(),
                raw.clone()
            ]
            .concat()
        );
        assert!(stream.direct_read_active());
        assert!(!stream.direct_write_active());
        assert_eq!(observation.lock().unwrap().read_switches, 1);
        assert_eq!(observation.lock().unwrap().write_switches, 0);
        drop(stream);
        assert_eq!(drops.load(Ordering::SeqCst), 1);
    }
}

#[tokio::test]
async fn first_peer_frame_can_establish_read_eligibility_and_direct_boundary() {
    let terminal = [hello(true), record(23, &[0x43; 157])].concat();
    for chop in [1, 19, 8192] {
        let framed = Encoder::new(UUID)
            .frame(Command::DirectRequested, &terminal, &[0x11; 79])
            .unwrap();
        let mut stream = stream(framed, Vec::new(), b"later-raw".to_vec(), chop);
        stream.write_all(&hello(false)).await.unwrap();
        stream.flush().await.unwrap();
        assert_eq!(stream.inspection().eligibility(), tls::Eligibility::Pending);
        assert!(
            !stream
                .inspection()
                .application_record_seen(tls::Direction::ClientToServer)
        );
        let mut response = Vec::new();
        stream.read_to_end(&mut response).await.unwrap();
        assert_eq!(response, [terminal.clone(), b"later-raw".to_vec()].concat());
        assert!(stream.direct_read_active());
        assert!(!stream.direct_write_active());
        assert!(stream.write_padding_active());
    }
}

#[tokio::test]
async fn direct_write_flush_is_cancellation_safe_and_never_replays_or_interleaves() {
    let peer = Encoder::new(UUID)
        .frame(Command::Continue, &hello(true), &[])
        .unwrap();
    let mut stream = stream(peer, Vec::new(), Vec::new(), 7);
    let observation = stream.inner.as_ref().unwrap().observation.clone();
    let blocked = stream.inner.as_ref().unwrap().blocked_flush.clone();
    hellos(&mut stream).await;
    let terminal = record(23, &[0x72; 16384]);
    stream.write_all(&terminal).await.unwrap();
    assert!(!stream.direct_write_active());
    blocked.store(true, Ordering::SeqCst);
    assert!(
        tokio::time::timeout(Duration::from_millis(10), stream.flush())
            .await
            .is_err()
    );
    assert!(stream.write_direct_pending);
    assert_eq!(observation.lock().unwrap().write_switches, 0);
    let before = observation.lock().unwrap().writes.clone();
    assert!(
        tokio::time::timeout(Duration::from_millis(10), stream.write(b"must-wait"))
            .await
            .is_err()
    );
    assert_eq!(observation.lock().unwrap().writes, before);
    blocked.store(false, Ordering::SeqCst);
    stream.flush().await.unwrap();
    assert!(stream.direct_write_active());
    assert!(!stream.direct_read_active());
    stream.write_all(b"raw-after-flush").await.unwrap();
    stream.shutdown().await.unwrap();
    stream.shutdown().await.unwrap();
    let observation = observation.lock().unwrap();
    assert_eq!(observation.write_switches, 1);
    assert_eq!(observation.shutdowns, 1);
    let mut wire = Vec::new();
    let mut raw = Vec::new();
    let mut raw_seen = false;
    for (direct, part) in &observation.writes {
        if *direct {
            raw_seen = true;
            raw.extend_from_slice(part);
        } else {
            assert!(!raw_seen, "outer ciphertext after raw transition");
            wire.extend_from_slice(part);
        }
    }
    assert_eq!(raw, b"raw-after-flush");
    let mut decoder = Decoder::new(UUID);
    let mut offset = 0;
    let mut payload = Vec::new();
    let mut terminal_command = None;
    while offset < wire.len() {
        let step = decoder.decode(&wire[offset..]).unwrap();
        offset += step.consumed;
        payload.extend_from_slice(step.payload);
        terminal_command = step.boundary;
    }
    assert_eq!(payload, [hello(false), terminal].concat());
    assert_eq!(terminal_command, Some(Command::DirectRequested));
}

#[tokio::test]
async fn direct_request_at_partial_inner_record_refuses_and_releases_both_directions() {
    let mut incomplete = record(23, &[0x31; 113]);
    incomplete.pop();
    let mut stream = stream(
        peer_frames(
            Command::DirectRequested,
            &incomplete,
            &[],
            b"forbidden-tail",
        ),
        b"forbidden-residual".to_vec(),
        b"forbidden-raw".to_vec(),
        8192,
    );
    let observation = stream.inner.as_ref().unwrap().observation.clone();
    let drops = stream.inner.as_ref().unwrap().drops.clone();
    hellos(&mut stream).await;
    let mut output = [0; 1024];
    assert_eq!(
        stream.read(&mut output).await.unwrap_err().kind(),
        io::ErrorKind::PermissionDenied
    );
    assert_eq!(output, [0; 1024]);
    assert_eq!(observation.lock().unwrap().read_switches, 0);
    assert_eq!(drops.load(Ordering::SeqCst), 1);
    assert_eq!(
        stream.write(b"no fallback").await.unwrap_err().kind(),
        io::ErrorKind::PermissionDenied
    );
}

#[tokio::test]
async fn no_direct_transition_until_terminal_padding_is_complete() {
    let terminal = record(23, &[0x24; 100]);
    let complete = peer_frames(Command::DirectRequested, &terminal, &[0x11; 100], &[]);
    let mut stream = stream(
        complete[..complete.len() - 1].to_vec(),
        Vec::new(),
        b"raw".to_vec(),
        8192,
    );
    let observation = stream.inner.as_ref().unwrap().observation.clone();
    hellos(&mut stream).await;
    let mut received = vec![0; terminal.len()];
    stream.read_exact(&mut received).await.unwrap();
    assert_eq!(received, terminal);
    assert!(
        tokio::time::timeout(Duration::from_millis(10), stream.read(&mut [0; 1]))
            .await
            .is_err()
    );
    assert!(!stream.direct_read_active());
    assert_eq!(observation.lock().unwrap().read_switches, 0);
    stream.inner.as_mut().unwrap().outer.get_mut().push(0x11);
    let mut tail = Vec::new();
    stream.read_to_end(&mut tail).await.unwrap();
    assert_eq!(tail, b"raw");
    assert_eq!(observation.lock().unwrap().read_switches, 1);
}

#[tokio::test]
async fn write_half_close_does_not_drop_later_direct_downlink() {
    let terminal = record(23, &[0x24; 300]);
    let mut stream = stream(
        peer_frames(Command::DirectRequested, &terminal, &[], &[]),
        Vec::new(),
        b"late-raw".to_vec(),
        31,
    );
    let drops = stream.inner.as_ref().unwrap().drops.clone();
    hellos(&mut stream).await;
    stream.write_all(&record(23, &[0x91; 70])).await.unwrap();
    stream.shutdown().await.unwrap();
    assert!(stream.direct_write_active());
    assert_eq!(drops.load(Ordering::SeqCst), 0);
    let mut response = Vec::new();
    stream.read_to_end(&mut response).await.unwrap();
    assert_eq!(response, [terminal, b"late-raw".to_vec()].concat());
    assert!(stream.direct_read_active());
}

#[tokio::test]
async fn abort_pending_direct_flush_drops_the_only_owner() {
    let peer = Encoder::new(UUID)
        .frame(Command::Continue, &hello(true), &[])
        .unwrap();
    let mut stream = stream(peer, Vec::new(), Vec::new(), 8192);
    let blocked = stream.inner.as_ref().unwrap().blocked_flush.clone();
    let drops = stream.inner.as_ref().unwrap().drops.clone();
    hellos(&mut stream).await;
    stream.write_all(&record(23, &[0x91; 70])).await.unwrap();
    blocked.store(true, Ordering::SeqCst);
    poll_fn(|cx| {
        assert!(Pin::new(&mut stream).poll_flush(cx).is_pending());
        Poll::Ready(())
    })
    .await;
    stream.abort();
    assert_eq!(drops.load(Ordering::SeqCst), 1);
    assert_eq!(stream.buffered_bytes(), 0);
    assert_eq!(
        stream.flush().await.unwrap_err().kind(),
        io::ErrorKind::Interrupted
    );
}

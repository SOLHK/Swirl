//! Local control harness for integration tests. Secrets travel over stdin, never
//! command-line arguments; stdout returns only control state and fixed errors.
use std::io::{self, BufRead, Write};
fn main() {
    let mut controller = swirl_api::Controller::default();
    let mut input = io::stdin().lock();
    let mut output = io::stdout().lock();
    loop {
        let mut line = Vec::new();
        // Bound command growth before parsing. A too-large line ends the harness.
        loop {
            let Ok(buf) = input.fill_buf() else {
                return;
            };
            if buf.is_empty() {
                return;
            }
            let n = buf
                .iter()
                .position(|b| *b == b'\n')
                .map_or(buf.len(), |i| i + 1);
            if line.len() + n > 1024 * 1024 {
                return;
            }
            line.extend_from_slice(&buf[..n]);
            input.consume(n);
            if line.ends_with(b"\n") {
                break;
            }
        }
        let response = controller.dispatch(&line);
        if writeln!(output, "{response}")
            .and_then(|_| output.flush())
            .is_err()
        {
            return;
        }
    }
}

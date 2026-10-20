// Swirl's test instrumentation around the unmodified official Xray REALITY
// server. This file implements no REALITY/TLS protocol and is not linked into
// Swirl Core or the Qt application. One process handles one loopback test.
package main

import (
	"bufio"
	"bytes"
	"context"
	"crypto"
	"crypto/ecdh"
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/big"
	"net"
	"os"
	"runtime"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	"github.com/xtls/reality"
	xrayreality "github.com/xtls/xray-core/transport/internet/reality"
)

var xrayCommit = "unverified"
var realityVersion = "unverified"

const serverName = "swirl-reality.test"
const maxApplication = 1024 * 1024

type request struct {
	Mode       string `json:"mode"`
	Group      string `json:"group"`
	ReadChunk  int    `json:"read_chunk"`
	WriteChunk int    `json:"write_chunk"`
	TimeoutMS  int    `json:"timeout_ms"`
}

type report struct {
	Event                      string `json:"event"`
	Status                     string `json:"status"`
	HandshakeComplete          bool   `json:"handshake_complete"`
	ClientHelloAuthenticated   bool   `json:"client_hello_authenticated"`
	ClientFinishedVerified     bool   `json:"client_finished_verified"`
	TLSVersion                 uint16 `json:"tls_version"`
	Group                      uint16 `json:"group"`
	CipherSuite                uint16 `json:"cipher_suite"`
	ReceivedBytes              int    `json:"received_bytes"`
	SentBytes                  int    `json:"sent_bytes"`
	ReceivedSHA256             string `json:"received_sha256"`
	SentSHA256                 string `json:"sent_sha256"`
	CloseNotifyReceived        bool   `json:"close_notify_received"`
	CloseNotifySent            bool   `json:"close_notify_sent"`
	TransportEOF               bool   `json:"transport_eof"`
	ActiveConnections          int64  `json:"active_connections"`
	CamouflageApplicationBytes int64  `json:"camouflage_application_bytes"`
	Error                      string `json:"error,omitempty"`
}

func emit(value any) error { return json.NewEncoder(os.Stdout).Encode(value) }

// A real net.TCPConn remains underneath the wrapper. Read deliberately exposes
// short reads; Write splits transport writes while retaining net.Conn's rule
// that a successful write consumes the entire supplied buffer. CloseWrite is
// required by upstream's fallback cleanup, including rejected authentication.
type observedConn struct {
	*net.TCPConn
	readChunk  int
	writeChunk int
	eof        atomic.Bool
	hello      serverHelloObserver
}

// Upstream's REALITY-specific handshake path does not populate
// ConnectionState.CurveID. Observe the actual plaintext ServerHello instead
// of substituting the fixture's requested group. This bounded parser is only
// telemetry: it never alters, authenticates or decrypts protocol bytes.
type serverHelloObserver struct {
	records   []byte
	handshake []byte
	done      bool
	err       error
	group     uint16
	version   uint16
	cipher    uint16
}

func (o *serverHelloObserver) fail() {
	o.err = errors.New("malformed or missing wire ServerHello metadata")
	o.done = true
	o.records, o.handshake = nil, nil
}

func (o *serverHelloObserver) feed(data []byte) {
	if o.done {
		return
	}
	if len(o.records)+len(o.handshake)+len(data) > 65536 {
		o.fail()
		return
	}
	o.records = append(o.records, data...)
	for len(o.records) >= 5 {
		n := int(binary.BigEndian.Uint16(o.records[3:5]))
		if n > 16384 {
			o.fail()
			return
		}
		if len(o.records) < 5+n {
			return
		}
		kind, body := o.records[0], o.records[5:5+n]
		if kind == 22 {
			o.handshake = append(o.handshake, body...)
		} else if kind != 20 || len(body) != 1 || body[0] != 1 {
			o.fail()
			return
		}
		o.records = o.records[5+n:]
		if len(o.handshake) < 4 {
			continue
		}
		size := int(o.handshake[1])<<16 | int(o.handshake[2])<<8 | int(o.handshake[3])
		if o.handshake[0] != 2 || size > 16384 {
			o.fail()
			return
		}
		if len(o.handshake) < 4+size {
			continue
		}
		if !o.parse(o.handshake[4 : 4+size]) {
			o.fail()
			return
		}
		o.done = true
		o.records, o.handshake = nil, nil
		return
	}
}

func (o *serverHelloObserver) parse(body []byte) bool {
	if len(body) < 40 || binary.BigEndian.Uint16(body[:2]) != tls.VersionTLS12 {
		return false
	}
	sessionSize := int(body[34])
	if sessionSize > 32 || len(body) < 35+sessionSize+5 {
		return false
	}
	position := 35 + sessionSize
	o.cipher = binary.BigEndian.Uint16(body[position : position+2])
	if body[position+2] != 0 {
		return false
	}
	position += 3
	extensionSize := int(binary.BigEndian.Uint16(body[position : position+2]))
	position += 2
	if len(body)-position != extensionSize {
		return false
	}
	for position < len(body) {
		if len(body)-position < 4 {
			return false
		}
		kind := binary.BigEndian.Uint16(body[position : position+2])
		n := int(binary.BigEndian.Uint16(body[position+2 : position+4]))
		position += 4
		if len(body)-position < n {
			return false
		}
		value := body[position : position+n]
		switch kind {
		case 43:
			if n != 2 || o.version != 0 {
				return false
			}
			o.version = binary.BigEndian.Uint16(value)
		case 51:
			if n < 4 || o.group != 0 || int(binary.BigEndian.Uint16(value[2:4])) != n-4 {
				return false
			}
			o.group = binary.BigEndian.Uint16(value[:2])
		}
		position += n
	}
	return o.group != 0 && o.version == tls.VersionTLS13
}

func (c *observedConn) Read(buffer []byte) (int, error) {
	if len(buffer) > c.readChunk {
		buffer = buffer[:c.readChunk]
	}
	n, err := c.TCPConn.Read(buffer)
	if errors.Is(err, io.EOF) {
		c.eof.Store(true)
	}
	return n, err
}

func (c *observedConn) Write(buffer []byte) (int, error) {
	total := 0
	for len(buffer) > 0 {
		end := min(len(buffer), c.writeChunk)
		n, err := c.TCPConn.Write(buffer[:end])
		c.hello.feed(buffer[:n])
		total += n
		buffer = buffer[n:]
		if err != nil {
			return total, err
		}
		if n == 0 {
			return total, io.ErrShortWrite
		}
	}
	return total, nil
}

type connectionSet struct {
	mu      sync.Mutex
	conns   map[net.Conn]struct{}
	active  atomic.Int64
	wg      sync.WaitGroup
	closing bool
}

func (s *connectionSet) add(conn net.Conn) bool {
	s.mu.Lock()
	if s.closing {
		s.mu.Unlock()
		conn.Close()
		return false
	}
	s.conns[conn] = struct{}{}
	s.active.Add(1)
	s.mu.Unlock()
	return true
}

func (s *connectionSet) done(conn net.Conn) {
	conn.Close()
	s.forget(conn)
}

func (s *connectionSet) forget(conn net.Conn) {
	s.mu.Lock()
	if _, exists := s.conns[conn]; exists {
		delete(s.conns, conn)
		s.active.Add(-1)
	}
	s.mu.Unlock()
}

func (s *connectionSet) closeAll() {
	s.mu.Lock()
	s.closing = true
	conns := make([]net.Conn, 0, len(s.conns))
	for conn := range s.conns {
		conns = append(conns, conn)
	}
	s.mu.Unlock()
	for _, conn := range conns {
		conn.Close()
	}
}

// Include the upstream's outbound camouflage socket in resource accounting.
// Close may be called by upstream and again by fixture cleanup; removal is
// idempotent and never happens before the underlying descriptor is closed.
type countedConn struct {
	net.Conn
	owner *connectionSet
}

func (c *countedConn) Close() error {
	err := c.Conn.Close()
	c.owner.forget(c)
	return err
}

func (c *countedConn) CloseWrite() error { return c.Conn.(*net.TCPConn).CloseWrite() }

func certificate(browser bool) (tls.Certificate, error) {
	// Offer both certificates through the standard TLS selection path. Chrome
	// does not advertise Ed25519; the existing native profile still uses it.
	generate := func() (crypto.Signer, error) {
		if browser {
			return ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
		}
		_, key, err := ed25519.GenerateKey(rand.Reader)
		return key, err
	}
	caKey, err := generate()
	if err != nil {
		return tls.Certificate{}, err
	}
	key, err := generate()
	if err != nil {
		return tls.Certificate{}, err
	}
	serial, err := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 128))
	if err != nil {
		return tls.Certificate{}, err
	}
	ca := &x509.Certificate{
		SerialNumber: serial, Subject: pkix.Name{CommonName: "Swirl ephemeral loopback CA"},
		NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour),
		KeyUsage: x509.KeyUsageCertSign, BasicConstraintsValid: true, IsCA: true,
		MaxPathLenZero: true,
	}
	caDER, err := x509.CreateCertificate(rand.Reader, ca, ca, caKey.Public(), caKey)
	if err != nil {
		return tls.Certificate{}, err
	}
	serial, err = rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 128))
	if err != nil {
		return tls.Certificate{}, err
	}
	template := &x509.Certificate{
		SerialNumber: serial,
		Subject:      pkix.Name{CommonName: serverName},
		DNSNames:     []string{serverName},
		NotBefore:    time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour),
		KeyUsage:              x509.KeyUsageDigitalSignature,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		BasicConstraintsValid: true,
	}
	der, err := x509.CreateCertificate(rand.Reader, template, ca, key.Public(), caKey)
	if err != nil {
		return tls.Certificate{}, err
	}
	return tls.Certificate{Certificate: [][]byte{der, caDER}, PrivateKey: key}, nil
}

func validate(input *request) error {
	if input.Mode == "" {
		input.Mode = "echo"
	}
	if input.Group == "" {
		input.Group = "hybrid"
	}
	if input.ReadChunk == 0 {
		input.ReadChunk = 4093
	}
	if input.WriteChunk == 0 {
		input.WriteChunk = 997
	}
	if input.TimeoutMS == 0 {
		input.TimeoutMS = 8000
	}
	switch input.Mode {
	case "echo", "unclean-eof", "stall-handshake", "stall-data", "observe-cancel":
	default:
		return errors.New("invalid fixture mode")
	}
	if input.Group != "x25519" && input.Group != "hybrid" {
		return errors.New("invalid fixture group")
	}
	if input.ReadChunk < 1 || input.ReadChunk > 16384 || input.WriteChunk < 1 || input.WriteChunk > 16384 || input.TimeoutMS < 100 || input.TimeoutMS > 20000 {
		return errors.New("fixture budget out of bounds")
	}
	return nil
}

func run(input request, result *report) error {
	deadline := time.Now().Add(time.Duration(input.TimeoutMS) * time.Millisecond)
	all := &connectionSet{conns: make(map[net.Conn]struct{})}
	var camouflageBytes atomic.Int64
	camouflage, err := net.ListenTCP("tcp4", &net.TCPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		return err
	}
	listener, err := net.ListenTCP("tcp4", &net.TCPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		camouflage.Close()
		return err
	}
	defer func() {
		listener.Close()
		camouflage.Close()
		all.closeAll()
		all.wg.Wait()
		result.ActiveConnections = all.active.Load()
		result.CamouflageApplicationBytes = camouflageBytes.Load()
	}()
	cert, err := certificate(false)
	if err != nil {
		return err
	}
	browserCert, err := certificate(true)
	if err != nil {
		return err
	}
	group := tls.X25519MLKEM768
	if input.Group == "x25519" {
		group = tls.X25519
	}
	targetTLS := &tls.Config{
		Certificates: []tls.Certificate{cert, browserCert}, MinVersion: tls.VersionTLS13,
		MaxVersion: tls.VersionTLS13, CurvePreferences: []tls.CurveID{group},
		SessionTicketsDisabled: true,
	}
	// This controlled target emits no post-handshake tickets or application
	// bytes. Seed the upstream's exported target-observation cache with that
	// exact known fact, avoiding its background Internet-style probes. No TLS,
	// certificate authentication, Finished or record-processing code is changed.
	for alpn := range 3 {
		key := camouflage.Addr().String() + " " + serverName + " " + strconv.Itoa(alpn)
		reality.GlobalPostHandshakeRecordsLens.Store(key, []int{})
	}
	all.wg.Add(1)
	go func() {
		defer all.wg.Done()
		for {
			raw, acceptErr := camouflage.AcceptTCP()
			if acceptErr != nil {
				return
			}
			if !all.add(raw) {
				return
			}
			all.wg.Add(1)
			go func() {
				defer all.wg.Done()
				defer all.done(raw)
				raw.SetDeadline(deadline)
				conn := tls.Server(raw, targetTLS)
				if conn.Handshake() != nil {
					return
				}
				buffer := make([]byte, 4096)
				for {
					n, readErr := conn.Read(buffer)
					camouflageBytes.Add(int64(n))
					if readErr != nil {
						return
					}
					if n > 0 {
						return
					} // invalid credentials must never send an application payload
				}
			}()
		}
	}()
	privateKey, err := ecdh.X25519().GenerateKey(rand.Reader)
	if err != nil {
		return err
	}
	var shortID [8]byte
	if _, err = io.ReadFull(rand.Reader, shortID[:]); err != nil {
		return err
	}
	settings := map[string]any{
		"host": "127.0.0.1", "port": listener.Addr().(*net.TCPAddr).Port,
		"server_name": serverName, "public_key_hex": hex.EncodeToString(privateKey.PublicKey().Bytes()),
		"short_id_hex": hex.EncodeToString(shortID[:]), "version": []int{26, 10, 17},
	}
	if err = emit(map[string]any{"event": "ready", "settings": settings}); err != nil {
		return err
	}
	listener.SetDeadline(deadline)
	raw, err := listener.AcceptTCP()
	if err != nil {
		return err
	}
	if !all.add(raw) {
		return net.ErrClosed
	}
	defer all.done(raw)
	raw.SetDeadline(deadline)
	raw.SetNoDelay(true)
	observed := &observedConn{TCPConn: raw, readChunk: input.ReadChunk, writeChunk: input.WriteChunk}
	defer func() { result.TransportEOF = observed.eof.Load() }()
	if input.Mode == "stall-handshake" || input.Mode == "observe-cancel" {
		// Hide TCPConn's promoted WriterTo fast path so every observed EOF
		// passes through our instrumented Read, including cancellation.
		_, err = io.Copy(io.Discard, struct{ io.Reader }{observed})
		if err == nil {
			result.Status = "cancelled"
			return nil
		}
		return err
	}
	config := &reality.Config{
		Type: "tcp", Dest: camouflage.Addr().String(), ServerNames: map[string]bool{serverName: true},
		PrivateKey: privateKey, ShortIds: map[[8]byte]bool{shortID: true}, MaxTimeDiff: time.Minute,
		SessionTicketsDisabled: true,
		DialContext: func(ctx context.Context, network, address string) (net.Conn, error) {
			// Never honor arbitrary upstream destinations: the only authorized
			// target for this fixture is its own in-process loopback TLS server.
			if network != "tcp" || address != camouflage.Addr().String() {
				return nil, errors.New("non-loopback fixture target refused")
			}
			conn, dialErr := (&net.Dialer{Deadline: deadline}).DialContext(ctx, network, address)
			if dialErr != nil {
				return nil, dialErr
			}
			conn.SetDeadline(deadline)
			counted := &countedConn{Conn: conn, owner: all}
			if !all.add(counted) {
				return nil, net.ErrClosed
			}
			return counted, nil
		},
	}
	server, err := xrayreality.Server(observed, config)
	if err != nil {
		result.Status = "authentication_rejected"
		result.Error = "upstream REALITY handshake rejected"
		return nil
	}
	conn, ok := server.(*xrayreality.Conn)
	if !ok {
		return errors.New("unexpected upstream server type")
	}
	state := conn.ConnectionState()
	result.HandshakeComplete = state.HandshakeComplete
	result.ClientFinishedVerified = state.HandshakeComplete
	result.ClientHelloAuthenticated = state.HandshakeComplete && conn.ClientShortId == shortID
	result.TLSVersion = state.Version
	result.Group = observed.hello.group
	result.CipherSuite = state.CipherSuite
	if !result.ClientHelloAuthenticated || !result.ClientFinishedVerified || result.TLSVersion != tls.VersionTLS13 ||
		!observed.hello.done || observed.hello.err != nil || observed.hello.version != state.Version ||
		observed.hello.cipher != state.CipherSuite || result.Group != uint16(group) ||
		(state.CurveID != 0 && uint16(state.CurveID) != result.Group) {
		return errors.New("upstream completed without required authentication or TLS state")
	}
	receivedHash, sentHash := sha256.New(), sha256.New()
	defer func() {
		result.ReceivedSHA256 = hex.EncodeToString(receivedHash.Sum(nil))
		result.SentSHA256 = hex.EncodeToString(sentHash.Sum(nil))
	}()
	buffer := make([]byte, 4093)
	for {
		n, readErr := conn.Read(buffer)
		result.ReceivedBytes += n
		if result.ReceivedBytes > maxApplication {
			return errors.New("application budget exceeded")
		}
		receivedHash.Write(buffer[:n])
		if input.Mode != "stall-data" && n > 0 {
			for offset := 0; offset < n; {
				end := min(offset+997, n)
				written, writeErr := conn.Write(buffer[offset:end])
				result.SentBytes += written
				sentHash.Write(buffer[offset : offset+written])
				offset += written
				if writeErr != nil {
					return writeErr
				}
				if written == 0 {
					return io.ErrShortWrite
				}
			}
		}
		if readErr != nil {
			// Upstream Go TLS tolerates TCP EOF at a record boundary. Explicitly
			// distinguish that event from its authenticated close_notify EOF.
			if errors.Is(readErr, io.EOF) && !observed.eof.Load() {
				result.CloseNotifyReceived = true
				if input.Mode == "unclean-eof" {
					result.Status = "intentional_unclean_eof"
					return raw.Close()
				}
				if err = conn.Close(); err != nil {
					return err
				}
				result.CloseNotifySent = true
				result.Status = "completed"
				return nil
			}
			if input.Mode == "stall-data" && (observed.eof.Load() || errors.Is(readErr, io.ErrUnexpectedEOF)) {
				result.Status = "cancelled"
				return nil
			}
			return readErr
		}
	}
}

func main() {
	if len(os.Args) == 2 && os.Args[1] == "--version" {
		if err := emit(map[string]any{"event": "version", "xray_commit": xrayCommit,
			"reality_version": realityVersion, "go_version": runtime.Version()}); err != nil {
			os.Exit(1)
		}
		return
	}
	input := request{}
	reader := bufio.NewReader(io.LimitReader(os.Stdin, 16385))
	line, err := reader.ReadBytes('\n')
	if err != nil && !errors.Is(err, io.EOF) {
		fmt.Fprintln(os.Stderr, "fixture input read failed")
		os.Exit(1)
	}
	if len(line) > 16384 {
		fmt.Fprintln(os.Stderr, "fixture input too large")
		os.Exit(1)
	}
	decoder := json.NewDecoder(bytes.NewReader(line))
	decoder.DisallowUnknownFields()
	if err = decoder.Decode(&input); err == nil {
		var extra any
		if decoder.Decode(&extra) != io.EOF {
			err = errors.New("trailing fixture input")
		}
	}
	if err == nil {
		err = validate(&input)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "invalid fixture input")
		os.Exit(1)
	}
	result := &report{Event: "result", Status: "error"}
	err = run(input, result)
	if err != nil {
		var networkError net.Error
		if errors.As(err, &networkError) && networkError.Timeout() {
			result.Status, result.Error = "timeout", "fixture I/O deadline expired"
		} else {
			result.Status, result.Error = "error", "fixture transport or invariant failed"
			fmt.Fprintf(os.Stderr, "fixture failure: %T: %v\n", err, err)
		}
	}
	if emit(result) != nil || err != nil || result.ActiveConnections != 0 {
		os.Exit(1)
	}
}

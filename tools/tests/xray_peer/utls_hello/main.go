// This test-only program obtains the wire ClientHello from the unmodified uTLS
// dependency pinned by Xray's verified go.mod and go.sum. It does not contain a
// copied profile, connect to a server, or implement any Swirl product transport.
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"runtime"
	"runtime/debug"

	utls "github.com/refraction-networking/utls"
)

var xrayCommit = "unverified"

const profile = "HelloChrome_133"

func run() error {
	serverName := flag.String("server-name", "swirl-fingerprint.test", "Synthetic first-connection SNI")
	version := flag.Bool("version", false, "Print the actual compiled dependency identity")
	flag.Parse()
	if flag.NArg() != 0 || *serverName == "" {
		return fmt.Errorf("a server name and no positional arguments are required")
	}
	info, ok := debug.ReadBuildInfo()
	if !ok {
		return fmt.Errorf("Go build identity is unavailable")
	}
	var dependency *debug.Module
	for _, module := range info.Deps {
		if module.Path == "github.com/refraction-networking/utls" {
			dependency = module
		}
	}
	if dependency == nil || dependency.Replace != nil || dependency.Sum == "" {
		return fmt.Errorf("the original checksum-verified uTLS dependency is required")
	}
	result := map[string]any{
		"event":       "version",
		"profile":     profile,
		"go_version":  runtime.Version(),
		"xray_commit": xrayCommit,
		"utls": map[string]string{
			"module": dependency.Path, "version": dependency.Version, "sum": dependency.Sum,
		},
		"ech_encoded_inner_lengths": utls.BoringGREASEECH().CandidatePayloadLens,
	}
	if !*version {
		// Building the first handshake only needs configuration and cryptographic
		// randomness. A nil net.Conn makes an accidental network operation fail.
		client := utls.UClient(nil, &utls.Config{
			ServerName: *serverName,
			NextProtos: []string{"h2", "http/1.1"},
		}, utls.HelloChrome_133)
		if err := client.BuildHandshakeState(); err != nil {
			return err
		}
		hello := client.HandshakeState.Hello.Raw
		if len(hello) < 4 || hello[0] != 1 {
			return fmt.Errorf("uTLS did not marshal a ClientHello handshake")
		}
		digest := sha256.Sum256(hello)
		result["event"] = "client_hello"
		result["server_name"] = *serverName
		result["handshake_hex"] = hex.EncodeToString(hello)
		result["handshake_sha256"] = hex.EncodeToString(digest[:])
	}
	return json.NewEncoder(os.Stdout).Encode(result)
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

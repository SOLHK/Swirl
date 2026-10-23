use std::env;

// The product build supplies a content digest, not a timestamp. Standalone Cargo
// harnesses are deliberately distinguishable from a paired Qt product DLL.
fn main() {
    println!("cargo::rerun-if-changed=build.rs");
    for key in ["SWIRL_BUILD_ID", "SWIRL_SOURCE_SHA"] {
        println!("cargo::rerun-if-env-changed={key}");
        let value = env::var(key).unwrap_or_else(|_| "standalone".to_owned());
        assert!(
            !value.is_empty()
                && value.len() <= 64
                && value
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b)),
            "invalid product build identity"
        );
        if key == "SWIRL_BUILD_ID" && value != "standalone" {
            assert!(
                value.len() == 64 && value.bytes().all(|b| b.is_ascii_hexdigit()),
                "product build ID must be a SHA-256 digest"
            );
        }
        println!("cargo::rustc-env={key}={value}");
    }
    let target = env::var("TARGET").expect("Cargo target is required");
    assert!(
        target.len() <= 128
            && target
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b)),
        "invalid Cargo target"
    );
    println!("cargo::rustc-env=SWIRL_BUILD_TARGET={target}");
}

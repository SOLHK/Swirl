use std::{
    fs,
    path::{Path, PathBuf},
    sync::atomic::{AtomicUsize, Ordering},
};
use swirl_core::Core;
use swirl_routing::load_rules_from_directory;
use swirl_subscription::Config;

static NEXT_DIRECTORY: AtomicUsize = AtomicUsize::new(0);

struct RuleDirectory(PathBuf);

impl RuleDirectory {
    fn new() -> Self {
        let path = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/china-rule-tests")
            .join(format!(
                "{}-{}",
                std::process::id(),
                NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed)
            ));
        fs::create_dir_all(&path).unwrap();
        Self(path)
    }

    fn copy(&self, name: &str) {
        let source = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../../src/Swirl.Quick/packaging/rules")
            .join(name);
        fs::copy(source, self.0.join(name)).unwrap();
    }

    fn config(&self) -> Config {
        let mut config = smart_config();
        config.china_rules_directory = Some(self.0.to_string_lossy().into_owned());
        config
    }
}

impl Drop for RuleDirectory {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}

fn smart_config() -> Config {
    Config::parse(
        br#"{"schema":1,"listen":"127.0.0.1:0","selected":"direct","smart_routing":true,"nodes":[{"id":"direct","outbound":{"type":"direct"}}]}"#,
    )
    .unwrap()
}

#[test]
fn explicit_valid_directory_loads_real_domain_and_ip_rules() {
    let directory = RuleDirectory::new();
    directory.copy("cn-domain.mrs");
    directory.copy("cn-ip.mrs");
    let (domains, ips) = load_rules_from_directory(&directory.0).unwrap();
    assert!(domains.matches_domain("www.baidu.com"));
    assert!(ips.matches_ip("114.114.114.114".parse().unwrap()));
    assert!(ips.matches_ip("240e:3a1:1000::1".parse().unwrap()));
    assert!(!ips.matches_ip("8.8.8.8".parse().unwrap()));

    let core = Core::start(directory.config()).unwrap();
    assert!(core.snapshot().unwrap().running);
}

#[test]
fn explicit_missing_directory_fails_without_bundled_fallback() {
    let parent = RuleDirectory::new();
    let mut config = smart_config();
    config.china_rules_directory = Some(parent.0.join("missing").to_string_lossy().into_owned());
    assert!(matches!(Core::start(config), Err("ChinaDomainRulesRead")));
}

#[test]
fn explicit_partial_directory_rejects_each_missing_file() {
    let missing_domain = RuleDirectory::new();
    missing_domain.copy("cn-ip.mrs");
    assert!(matches!(
        Core::start(missing_domain.config()),
        Err("ChinaDomainRulesRead")
    ));

    let missing_ip = RuleDirectory::new();
    missing_ip.copy("cn-domain.mrs");
    assert!(matches!(
        Core::start(missing_ip.config()),
        Err("ChinaIpRulesRead")
    ));
}

#[test]
fn explicit_tampered_or_truncated_rules_fail_closed() {
    let tampered = RuleDirectory::new();
    tampered.copy("cn-domain.mrs");
    tampered.copy("cn-ip.mrs");
    let mut bytes = fs::read(tampered.0.join("cn-domain.mrs")).unwrap();
    bytes.push(0);
    fs::write(tampered.0.join("cn-domain.mrs"), bytes).unwrap();
    assert!(matches!(
        Core::start(tampered.config()),
        Err("ChinaDomainRulesInvalid")
    ));

    let truncated = RuleDirectory::new();
    truncated.copy("cn-domain.mrs");
    fs::write(truncated.0.join("cn-ip.mrs"), [0u8; 3]).unwrap();
    assert!(matches!(
        Core::start(truncated.config()),
        Err("ChinaIpRulesInvalid")
    ));
}

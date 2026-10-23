//! Strict SIP022 credentials. SIP023 identity chains are a distinct extension.
use base64::{
    Engine,
    engine::general_purpose::{STANDARD, STANDARD_NO_PAD},
};

pub fn validate(password: &str, cipher: &str) -> Result<(), &'static str> {
    let length = match cipher {
        "2022-blake3-aes-128-gcm" => 16,
        "2022-blake3-aes-256-gcm" => 32,
        _ => return Err("Ss2022CipherUnsupported"),
    };
    if password.contains(':') {
        return Err("Ss2022IdentityChainUnsupported");
    }
    if password.len() > 44 {
        return Err("Ss2022Key");
    }
    let mut bytes = STANDARD
        .decode(password)
        .or_else(|_| STANDARD_NO_PAD.decode(password))
        .map_err(|_| "Ss2022Key")?;
    let valid = bytes.len() == length;
    bytes.fill(0);
    if !valid {
        return Err("Ss2022Key");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_only_exact_base64_keys_without_password_derivation() {
        for (cipher, size) in [
            ("2022-blake3-aes-128-gcm", 16),
            ("2022-blake3-aes-256-gcm", 32),
        ] {
            let key = vec![0x7b; size];
            assert_eq!(validate(&STANDARD.encode(&key), cipher), Ok(()));
            assert_eq!(validate(&STANDARD_NO_PAD.encode(&key), cipher), Ok(()));
            assert_eq!(validate("password", cipher), Err("Ss2022Key"));
            assert_eq!(
                validate(&STANDARD.encode(vec![0; size + 1]), cipher),
                Err("Ss2022Key")
            );
        }
    }

    #[test]
    fn optional_ciphers_and_identity_chain_are_explicitly_unsupported() {
        assert_eq!(
            validate("AA==", "2022-blake3-chacha20-poly1305"),
            Err("Ss2022CipherUnsupported")
        );
        assert_eq!(
            validate("one:two", "2022-blake3-aes-128-gcm"),
            Err("Ss2022IdentityChainUnsupported")
        );
    }
}

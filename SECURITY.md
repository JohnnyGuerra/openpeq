# Security Policy

## Reporting Security Concerns & Vulnerabilities

We take the security and integrity of `dac-peq-manager` seriously. Because this software interfaces with physical hardware via the WebHID API, protecting users' hardware and privacy is our top priority.

### How to Report

If you discover a potential security vulnerability, privilege issue, or hardware safety concern, please report it via any of the following channels:

1. **GitHub Private Security Advisory (Recommended):**
   - Open a private report via [GitHub Security Advisories](https://github.com/JohnnyGuerra/dac-peq-manager/security/advisories/new).
   - This keeps findings confidential until a fix can be verified and deployed.

2. **Direct Email:**
   - Email the maintainer directly at: `johnny.guerra@gmail.com`
   - Please include details on the vulnerability, steps to reproduce, affected browsers or hardware, and any proof-of-concept.

3. **Public GitHub Issues (Non-sensitive concerns):**
   - If it is a general question about sandboxing, permissions, or dependency audits, you are welcome to open a standard [GitHub Issue](https://github.com/JohnnyGuerra/dac-peq-manager/issues).

---

### Security Architecture & Sandboxing

For transparency, `dac-peq-manager` is designed with the following security principles:

- **Browser Sandbox:** The Web Flasher runs entirely client-side on GitHub Pages. No backend server, no proxy, no databases.
- **Explicit WebHID Device Consent:** Per W3C WebHID specifications, the website cannot detect or communicate with any USB device without the user explicitly clicking the device in the browser's native OS permission dialog.
- **Zero Network Telemetry:** No user data, audio streams, IP addresses, or device IDs are transmitted over the network. The app functions completely offline and can be cloned and hosted on `localhost`.
- **Hardware Safety Guardrails:**
  - Strict block on Conexant CX31993 OTP register writes to prevent permanent hardware damage.
  - Strict block on register `0x11` / `0x66` writes on Kiwi Ears Allegro Mini to prevent MCU volume attenuation lockouts.

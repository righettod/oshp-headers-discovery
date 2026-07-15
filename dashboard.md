
> 🕑 Last update 2026-07-15 16:08:39.

| Header name | Header direction | Fully classified | Classifier explanation | Validator explanation | Links |
| --- | --- | --- | --- | --- | --- |
| ACCESS-CONTROL | RESPONSE | True | Enforces cross-origin access control for resources |  | [RFC](https://www.w3.org/TR/2007/WD-access-control-20071126/#access-control0) |
| ACTIVATE-STORAGE-ACCESS | RESPONSE | True | Explicitly part of Security Considerations (§8) for CSRF protection and opt-in security boundary |  | [RFC](https://privacycg.github.io/storage-access-headers) - [SPEC](https://privacycg.github.io/storage-access-headers/#activate-storage-access-header) |
| AUTHENTICATION-INFO | RESPONSE | True | AUTHENTICATION-INFO is defined in RFC 7615 as security-related for HTTP authentication. |  | [RFC](https://www.rfc-editor.org/rfc/rfc9110.txt) |
| CONTENT-DIGEST | RESPONSE | True | Mitigates data corruption via integrity digests |  | [RFC](https://www.rfc-editor.org/rfc/rfc9530.txt) |
| CONTENT-SECURITY-POLICY-REPORT-ONLY | RESPONSE | True | Monitors violations, indirectly informing security posture |  | [RFC](https://www.w3.org/TR/CSP/#cspro-header) - [SPEC](https://w3c.github.io/webappsec-csp/#cspro-header) |
| CROSS-ORIGIN-EMBEDDER-POLICY-REPORT-ONLY | RESPONSE | True | Enforces cross-origin embedding policies, directly impacting security posture. |  | [RFC](https://html.spec.whatwg.org/multipage/origin.html#cross-origin-embedder-policy-report-only) |
| CROSS-ORIGIN-OPENER-POLICY-REPORT-ONLY | RESPONSE | True | Enforces cross-origin opener policies, controlling browsing context groups and reporting violations, directly impacting security posture. |  | [RFC](https://html.spec.whatwg.org/multipage/origin.html#cross-origin-opener-policy-report-only) |
| DPOP | RESPONSE | True | DPoP header binds token to public key, preventing unauthorized use |  | [RFC](https://www.rfc-editor.org/rfc/rfc9449.txt) |
| HOBAREG | RESPONSE | True | HOBA is a security mechanism for HTTP authentication using digital signatures, directly impacting security posture by authenticating users and protecting against password-based vulnerabilities. |  | [RFC](https://www.rfc-editor.org/rfc/rfc7486.txt) |
| INCLUDE-REFERRED-TOKEN-BINDING-ID | RESPONSE | True | Directly mitigates token replay attacks in federated sign-on scenarios |  | [RFC](https://www.rfc-editor.org/rfc/rfc8473.txt) |
| INTEGRITY-POLICY | RESPONSE | True | Explicitly part of a security mechanism (Subresource Integrity) to verify resource authenticity |  | [SPEC](https://w3c.github.io/webappsec-subresource-integrity/#integrity-policy-section) |
| INTEGRITY-POLICY-REPORT-ONLY | RESPONSE | True | Enforces integrity verification for subresources, mitigating tampering attacks |  | [SPEC](https://w3c.github.io/webappsec-subresource-integrity/#integrity-policy-section) |
| ORIGIN-AGENT-CLUSTER | RESPONSE | True | Enforces origin-keyed agent clustering, impacting same-origin isolation and security |  | [RFC](https://html.spec.whatwg.org/multipage/origin.html#origin-agent-cluster) - [SPEC](https://html.spec.whatwg.org/multipage/browsers.html#origin-agent-cluster) |
| PERMISSIONS-POLICY-REPORT-ONLY | RESPONSE | True | Controls feature permissions, limiting API access based on origin |  | [SPEC](https://w3c.github.io/webappsec-permissions-policy/#permissions-policy-report-only-http-header-field) |
| PROXY-AUTHENTICATE | RESPONSE | True | PROXY-AUTHENTICATE authenticates clients to proxies, protecting credentials. |  | [RFC](https://www.rfc-editor.org/rfc/rfc9110.txt) - [SPEC](https://httpwg.org/specs/rfc9110.html#field.proxy-authenticate) |
| SEC-PRIVATE-STATE-TOKEN | RESPONSE | True | Directly enables secure authentication with cryptographic tokens, preventing token misuse and ensuring token integrity. |  | [SPEC](https://wicg.github.io/trust-token-api/#sec-private-state-token) |
| SEC-PRIVATE-STATE-TOKEN-LIFETIME | RESPONSE | True | Governs token expiration, directly impacting security posture by limiting record validity. |  | [SPEC](https://wicg.github.io/trust-token-api/#sec-private-state-token-lifetime) |
| SEC-SECURE-SESSION-ID | RESPONSE | True | Mitigates session theft, protects authentication artifacts via cryptographic key management. |  | [SPEC](https://w3c.github.io/webappsec-dbsc/#header-sec-secure-session-id) |
| SECURE-SESSION-CHALLENGE | RESPONSE | True | Mitigates session theft via private key protection |  | [SPEC](https://w3c.github.io/webappsec-dbsc/#header-secure-session-challenge) |
| SECURE-SESSION-REGISTRATION | RESPONSE | True | Protects session credentials via private key binding, mitigating cookie theft. |  | [SPEC](https://w3c.github.io/webappsec-dbsc/#header-secure-session-registration) |
| SECURE-SESSION-RESPONSE | RESPONSE | True | Directly mitigates session theft by cryptographically binding credentials to a device |  | [SPEC](https://w3c.github.io/webappsec-dbsc/#header-secure-session-registration) |
| SECURE-SESSION-SKIPPED | RESPONSE | True | Part of DBSC security mechanism to signal skipped sessions for security policy reasons |  | [SPEC](https://w3c.github.io/webappsec-dbsc/#header-secure-session-skipped) |
| SET-COOKIE2 | RESPONSE | True | RFC explicitly frames cookies as security/privacy mechanisms |  | [RFC](https://www.rfc-editor.org/rfc/rfc2965.txt) |
| SET-LOGIN | RESPONSE | True | Directly controls login status, impacting authentication state security. |  | [SPEC](https://w3c-fedid.github.io/login-status/#login-status-http) |
| SIGNATURE | RESPONSE | True | SIGNATURE header provides message authenticity and integrity, directly impacting security posture. |  | [RFC](https://www.rfc-editor.org/rfc/rfc9421.txt) - [SPEC](https://httpwg.org/specs/rfc9421.html#signature-header) |
| SPECULATION-RULES | RESPONSE | True | Explicit Security Considerations section in RFC |  | [SPEC](https://html.spec.whatwg.org/multipage/speculative-loading.html#the-speculation-rules-header) |
| WANT-CONTENT-DIGEST | RESPONSE | True | Enables detection of data corruption, supporting end-to-end integrity |  | [RFC](https://www.rfc-editor.org/rfc/rfc9530.txt) |
| WWW-AUTHENTICATE | RESPONSE | True | WWW-Authenticate is used for HTTP authentication, which directly impacts security posture by managing access credentials. |  | [RFC](https://www.rfc-editor.org/rfc/rfc9110.txt) - [SPEC](https://httpwg.org/specs/rfc9110.html#field.www-authenticate) |

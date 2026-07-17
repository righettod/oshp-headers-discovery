
> 🕑 Last update 2026-07-17 12:59:51.

| Header name | Header direction | Fully classified | Classifier explanation | Validator explanation | Links |
| --- | --- | --- | --- | --- | --- |
| CONTENT-SECURITY-POLICY-REPORT-ONLY | RESPONSE | True | Monitors violations, indirectly informing security posture |  | [RFC](https://www.w3.org/TR/CSP/#cspro-header) - [SPEC](https://w3c.github.io/webappsec-csp/#cspro-header) |
| CROSS-ORIGIN-EMBEDDER-POLICY-REPORT-ONLY | RESPONSE | True | Enforces cross-origin embedding policies, directly impacting security posture. |  | [RFC](https://html.spec.whatwg.org/multipage/origin.html#cross-origin-embedder-policy-report-only) |
| CROSS-ORIGIN-OPENER-POLICY-REPORT-ONLY | RESPONSE | True | Enforces cross-origin opener policies, controlling browsing context groups and reporting violations, directly impacting security posture. |  | [RFC](https://html.spec.whatwg.org/multipage/origin.html#cross-origin-opener-policy-report-only) |
| INTEGRITY-POLICY | RESPONSE | True | Explicitly part of a security mechanism (Subresource Integrity) to verify resource authenticity |  | [SPEC](https://w3c.github.io/webappsec-subresource-integrity/#integrity-policy-section) |
| INTEGRITY-POLICY-REPORT-ONLY | RESPONSE | True | Enforces integrity verification for subresources, mitigating tampering attacks |  | [SPEC](https://w3c.github.io/webappsec-subresource-integrity/#integrity-policy-section) |
| ORIGIN-AGENT-CLUSTER | RESPONSE | True | Enforces origin-keyed agent clustering, impacting same-origin isolation and security |  | [RFC](https://html.spec.whatwg.org/multipage/origin.html#origin-agent-cluster) - [SPEC](https://html.spec.whatwg.org/multipage/browsers.html#origin-agent-cluster) |
| PERMISSIONS-POLICY-REPORT-ONLY | RESPONSE | True | Controls feature permissions, limiting API access based on origin |  | [SPEC](https://w3c.github.io/webappsec-permissions-policy/#permissions-policy-report-only-http-header-field) |
| SECURE-SESSION-CHALLENGE | RESPONSE | True | Mitigates session theft via private key protection |  | [SPEC](https://w3c.github.io/webappsec-dbsc/#header-secure-session-challenge) |
| SECURE-SESSION-REGISTRATION | RESPONSE | True | Protects session credentials via private key binding, mitigating cookie theft. |  | [SPEC](https://w3c.github.io/webappsec-dbsc/#header-secure-session-registration) |

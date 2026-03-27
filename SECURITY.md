# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it responsibly.

### How to Report

**Please DO NOT file a public GitHub issue for security vulnerabilities.**

Report security vulnerabilities by sending an email to: **majunjie@apache.org**

Include the following information in your report:

- Type of vulnerability (e.g., authentication bypass, injection, data exposure)
- Full paths of source file(s) related to the vulnerability
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact assessment of the vulnerability

### What to Expect

After reporting a vulnerability, you can expect:

1. **Acknowledgment**: We will acknowledge receipt of your report within 48 hours
2. **Initial Assessment**: We will perform an initial assessment to determine the severity and validity
3. **Regular Updates**: We will keep you informed of our progress
4. **Resolution**: We will work on a fix and coordinate disclosure

### Disclosure Policy

We follow a **90-day coordinated disclosure** timeline:

- **Day 0**: Vulnerability is identified and reported
- **Day 1-30**: Vendor investigates and develops a fix
- **Day 31-90**: Fix is tested and a release is prepared
- **Day 90**: Public disclosure (if no fix is available, we will work with the reporter to determine an appropriate timeline)

### What We Consider Security Vulnerabilities

The following are considered security vulnerabilities and should be reported:

- **Authentication/Authorization issues**: Bypass of authentication mechanisms or privilege escalation
- **Credential exposure**: Hardcoded credentials, API keys, tokens, or passwords in source code
- **Injection attacks**: SQL injection, command injection, or other injection vulnerabilities
- **Data exposure**: Unintended exposure of sensitive data, configuration, or credentials
- **Path traversal**: Access to files or resources outside of intended boundaries
- **Denial of Service**: Vulnerabilities that can cause service disruption
- **Dependency vulnerabilities**: Known vulnerabilities in third-party dependencies

### Scope

This security policy applies to the oVirt MCP Server codebase. Integration with oVirt/RHV systems is covered, but infrastructure-level issues (network security, host security, etc.) should be reported to your infrastructure team.

## Security Updates

Security updates will be released as patch versions (e.g., 0.1.1) and announced through:

- GitHub Security Advisories
- Release notes

## Acknowledgments

We appreciate the efforts of security researchers and will acknowledge responsible reporters in our security advisories (unless you prefer to remain anonymous).

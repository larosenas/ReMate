# Security policy

## Supported versions

Only the latest version on the `main` branch receives security fixes.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Report it privately with GitHub's private vulnerability reporting: open the repository's **Security** tab and click **Report a vulnerability**. Include:

- what the problem is and where it is (file, endpoint or screen);
- the steps to reproduce it;
- what an attacker could do with it.

You will get an answer within a few days. Once the problem is confirmed, it will be fixed, and the fix will be published together with a security advisory that credits you, unless you prefer to stay anonymous.

## Scope

ReMate is designed to run on a company's internal network, without HTTPS ([ADR 0006](docs/adr/0006-despliegue-windows-sin-https.md)) and without a login: anyone on that network can use it. Only the admin mode is protected, by a password checked on the server ([ADR 0015](docs/adr/0015-modo-admin-con-contrasena.md)). Exposing ReMate to the internet is outside its intended use.

Reports about the admin mode, file uploads (`.eml`, `.msg`, PDF, Word and Excel), the data sent to the AI and leaks of configuration secrets are especially useful.

# Security

CloudPulse is a local portfolio application, not a hardened hosted multi-tenant service. Keep published ports on loopback. A shared random admin token protects dashboard data and management routes; it has no expiry, user roles, or session revocation. Rotate it by replacing the configured token and restarting the API/retention services.

Use the bootstrap script to generate unique credentials. It refuses to overwrite an existing `.env`; Unix creation mode is 0600. On Windows apply appropriate file ACLs. Agent keys are shown only at registration/rotation and stored as hashes. Do not log authorization headers, commit `.env`, or share the dashboard token. Use HTTPS with valid certificates for remote access; the agent enforces that requirement outside loopback. Nginx adds browser security headers.

The agent sends resource percentages and cumulative network counters; it does not collect processes, command lines, files, or packet contents. Collected host names and operational metrics may still be sensitive. Remove expired data with retention and maintain backups according to your needs. Dependencies and container base images need regular maintenance.

Report vulnerabilities privately to the repository owner using GitHub's private vulnerability reporting when enabled. Do not include real tokens or private machine information in public issues.

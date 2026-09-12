# Repository origin

This independent public repository starts from [FGT_Upgrade_Review commit f539387d691f1f5e42efe54940a9f05cd2693e6b](https://github.com/MoAl78741/FGT_Upgrade_Review/commit/f539387d691f1f5e42efe54940a9f05cd2693e6b). Existing copyright, license, and dependency notices are retained.

It has its own Git history, default branch, Docker image tag, edition defaults, README, and release workflow. It does not require the other repository as a submodule or package. Existing deployments and their data were not migrated.

The initial snapshot retains the tested shared application engine and both policy paths. This is repository/build separation, not a rewrite or physical removal of every other-edition module. Deployment capabilities remain enforced server-side. Future fixes must be ported deliberately between repositories; there is no automatic synchronization.

Only release-source files were copied. Runtime databases, PDFs, environment credentials, historical screenshots, and the old Git history were excluded. Historical source and authorship remain available through the origin link above.

# allrun53 Installation Guide

This guide sets up the Python simulator on Windows 11 and the optional native NETCONF stack in Ubuntu on WSL 2. Python, the CLI, and pytest run on Windows. Sysrepo, the operational-data plugin, and Netopeer2 run in WSL. You can use the offline simulator without installing the WSL NETCONF stack.

## 1. Prerequisites

- Windows 11 with a current WSL 2 installation.
- Ubuntu 22.04 LTS in WSL 2. The WSL NETCONF package snapshot was recorded on Ubuntu 22.04.1 LTS.
- Windows Python 3.11. The project requires exactly Python 3.11.
- A checkout of this project accessible from both Windows and WSL. The steps below assume the project is under your Windows user directory.
- Administrator access is needed only when installing/updating WSL or enabling Windows features. The WSL NETCONF setup uses `sudo` because it configures native services and creates a local smoke-test account.

Do not start installation of the WSL NETCONF stack if another service is using TCP port 830 or either `sysrepo-plugind.service` or `netopeer2.service` is active. The project scripts guard against taking over an unidentified stack; do not stop another service to make installation proceed.

## 2. Install or Check WSL

Open PowerShell as Administrator if WSL is not already installed. Install Ubuntu 22.04 with:

```powershell
wsl --install -d Ubuntu-22.04
```

Restart Windows if requested, launch Ubuntu 22.04 from the Start menu, and create its Linux username and password. These are separate from your Windows account. If WSL is already installed, update it instead:

```powershell
wsl --update
```

Check the distribution and WSL version in PowerShell:

```powershell
wsl --status
wsl --list --verbose
```

The Ubuntu distribution must show version `2`. If it shows version `1`, convert it from PowerShell:

```powershell
wsl --set-version Ubuntu-22.04 2
```

Set Ubuntu 22.04 as the default only if you want commands such as `wsl -e bash` to use it:

```powershell
wsl --set-default Ubuntu-22.04
```

### Enable systemd in WSL

The NETCONF scripts use `systemctl`. Recent Ubuntu installations may already have systemd enabled. In the Ubuntu terminal, check:

```bash
ps -p 1 -o comm=
systemctl is-system-running
```

If PID 1 is not `systemd`, edit `/etc/wsl.conf` and merge this setting into its existing contents. Do not overwrite other settings:

```ini
[boot]
systemd=true
```

Then, from PowerShell, restart WSL:

```powershell
wsl --shutdown
wsl -d Ubuntu-22.04
```

Re-run the checks in Ubuntu. A `degraded` system state can be normal in WSL; the important check is that `systemctl` responds and the project services can be managed.

## 3. Prepare the Project Path

Keep the checkout at a path available to both Windows and WSL. For example, a Windows checkout at:

```text
C:\Users\<windows-user>\src\grmis\allrun53
```

is available in Ubuntu as:

```text
/mnt/c/Users/<windows-user>/src/grmis/allrun53
```

In PowerShell, change to the actual project directory:

```powershell
Set-Location C:\Users\<windows-user>\src\grmis\allrun53
```

In Ubuntu, use the matching WSL path:

```bash
cd "/mnt/c/Users/<windows-user>/src/grmis/allrun53"
pwd
```

The WSL scripts derive their paths from the project directory, so run them from this checkout. Replace `<windows-user>` and the example parent directories with your actual path.

## 4. Set Up Windows Python

In PowerShell, verify Python 3.11 is available:

```powershell
py -3.11 --version
```

Create a project virtual environment and install the project with its test extras. This is the recommended setup because it installs the local package in editable mode along with `rich`, `pytest`, `pyang`, and `ncclient`:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe --version
```

The root `requirements.txt` lists the Python dependencies. If you prefer to install from that list, use it together with the local package installation:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

Use one installation method or the other. The `pyproject.toml` is the canonical package metadata; `requirements.txt` is a convenient direct-dependency list.

Check the local YANG module with pyang:

```powershell
.\.venv\Scripts\pyang.exe -p yang yang\ietf-power-and-energy@2026-11-01.yang
```

## 5. Install WSL Native Packages

In the Ubuntu terminal, first enter the project directory using its `/mnt/<drive>/...` path. Update the Ubuntu package index and install the packages listed by the project:

```bash
cd "/mnt/c/Users/<windows-user>/src/grmis/allrun53"
sudo apt-get update
xargs -r sudo apt-get install -y < install/apt-packages.txt
```

The package list supplies the compiler, Sysrepo, libyang, Netopeer2, and related development tools required to build the provider plugin. `install/apt-packages-lock.txt` records versions observed during validation; it is a host snapshot, not an apt pin file or an automated installer.

Verify the WSL environment. This check is read-only and makes no service or repository changes:

```bash
bash install/verify-wsl.sh
```

It prints the distribution and installed versions, service state, active Sysrepo repository, and whether the allrun53 repository has been provisioned. The message that the allrun53 repository is not provisioned is expected before the next step.

## 6. Review and Start the NETCONF Stack

Before authorizing setup, inspect the service and port state in Ubuntu:

```bash
systemctl show-environment | grep '^SYSREPO_REPOSITORY_PATH=' || true
systemctl is-active sysrepo-plugind.service || true
systemctl is-active netopeer2.service || true
ss -ltn | grep ':830' || true
```

If a service is active or TCP/830 is listening, identify which stack owns it before proceeding. The install and start scripts refuse to change configuration when the service/port state indicates that another or unidentified stack may be in use. Do not stop or reconfigure an unrelated stack.

After confirming that TCP/830 and the service names are available, explicitly authorize the project setup and start the stack:

```bash
sudo env ALLRUN53_ALLOW_HOST_CONFIG=1 bash scripts/wsl-netconf-start.sh
```

This command is intentionally guarded. It provisions the dedicated `/var/lib/grmis/allrun53/sysrepo` repository, installs the YANG modules and hardware hierarchy there, builds `netconf/plugins/green_snapshot_plugin.so`, configures the systemd environment for the project services, and starts `sysrepo-plugind` and Netopeer2. It also creates or updates the local `allrun53-smoke` Linux account and writes ncclient connection credentials to `runtime/netconf/connection.env`, setting its WSL mode to `600`. Because the checkout is on the Windows drive, also protect this file with appropriate Windows ACLs. Review this host configuration step before authorizing it. The opt-in applies to this command; it does not bypass the active-service or port checks.

Check the result:

```bash
bash scripts/wsl-netconf-status.sh
```

Expected results include running Sysrepo and Netopeer2 services, installed target YANG modules, the allrun53 repository path, and a NETCONF listener on port 830. The scripts use an isolated repository path and shared-memory prefix for allrun53.

Never commit or share `runtime/netconf/connection.env`; it contains a generated password. Keep the file local to this checkout.

## 7. Validate from Windows

With the WSL services running, return to PowerShell in the allrun53 project root. Run the tests that do not require a live NETCONF endpoint:

```powershell
.\.venv\Scripts\python.exe -m pytest --ignore=tests/netconf
```

The NETCONF integration tests use the credentials in `runtime/netconf/connection.env` and connect to the local endpoint or its configured WSL address fallback:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/netconf
```

The normal pytest configuration writes temporary test data under `runtime/pytest-tmp`; documentation-generation tests can refresh generated files under `docs/`.

To run the launcher, which checks or starts the WSL stack, runs the full test suite, then starts the GREEN event runtime:

```powershell
py .\run.py
```

If setup requires host configuration, the launcher asks for explicit authorization. You can also authorize that run in advance by setting `ALLRUN53_ALLOW_HOST_CONFIG=1` in the PowerShell environment, but the service and port guards remain active. `--auto` and `-n` runs are unattended: they authorize setup automatically (like `-f`) and never wait for ENTER. For an automatic event run with no delay:

```powershell
py .\run.py --auto --interval 0
```

To run only the offline simulator without WSL or NETCONF:

```powershell
.\.venv\Scripts\python.exe -m green --auto --interval 0
```

## 8. Stop the WSL Services

The launcher attempts to stop only the allrun53 services when it exits. If you started the services manually, stop them from Ubuntu with:

```bash
sudo bash scripts/wsl-netconf-stop.sh
```

The stop script checks that the active Sysrepo repository is the allrun53 repository. It does not remove the repository, modules, generated credentials, or systemd configuration. If it reports that it skipped stopping, inspect the service environment rather than stopping services manually.

## Troubleshooting

- **`systemctl` is unavailable or cannot connect:** confirm PID 1 is systemd in Ubuntu, edit `/etc/wsl.conf` without removing existing settings, run `wsl --shutdown`, then reopen Ubuntu.
- **The start script refuses because of TCP/830 or an active service:** do not kill the listener or stop the service blindly. Use `systemctl show-environment`, `systemctl status`, and `ss -ltnp` in Ubuntu to identify the owner. Proceed only when the stack is known and safe to use.
- **Windows NETCONF tests cannot connect:** confirm `bash scripts/wsl-netconf-status.sh` shows the listener, and confirm `runtime/netconf/connection.env` exists and is readable by your Windows account. The test fixture tries `localhost` first and then `NETCONF_HOST` from that file.
- **The virtual environment points to a missing Python installation:** recreate `.venv` with the installed Python 3.11 interpreter and reinstall with `python -m pip install -e ".[test]"`.
- **The native plugin fails to build:** rerun `sudo apt-get update` and install the current package list, then inspect the compiler output from `scripts/wsl-netconf-build-plugin.sh`.

See [README.md](README.md) for simulator behavior, controls, and architecture. The exact YANG revisions and source hashes are recorded in [the module manifest](install/yang-module-manifest.json).

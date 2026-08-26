# Firecracker MicroVM Setup

Firecracker provides the highest level of sandbox isolation in Blackbeard.
Each tool execution gets a dedicated VM with its own Linux kernel, providing
stronger isolation than libkrun (which wraps OCI containers with KVM).

Firecracker is Linux-only and requires KVM access. On macOS or systems without
KVM, Blackbeard automatically falls back to libkrun for the `microvm` tier.

## Prerequisites

- Linux host with KVM support (`/dev/kvm` must exist)
- Root or membership in the `kvm` group

Verify KVM access:

```bash
ls -la /dev/kvm
# crw-rw---- 1 root kvm 10, 232 ... /dev/kvm
```

## 1. Download Firecracker

Download the latest release from GitHub:

```bash
ARCH=$(uname -m)
FC_VERSION="1.12.0"

curl -fsSL "https://github.com/firecracker-microvm/firecracker/releases/download/v${FC_VERSION}/firecracker-v${FC_VERSION}-${ARCH}.tgz" \
  | tar -xz

sudo mv release-v${FC_VERSION}-${ARCH}/firecracker-v${FC_VERSION}-${ARCH} /usr/local/bin/firecracker
sudo chmod +x /usr/local/bin/firecracker

firecracker --version
```

## 2. Download Kernel Image

Firecracker provides pre-built kernel images alongside each release:

```bash
curl -fsSL "https://github.com/firecracker-microvm/firecracker/releases/download/v${FC_VERSION}/vmlinux-6.1-${ARCH}.bin" \
  -o /opt/firecracker/vmlinux.bin
```

Or build your own minimal kernel with only the features you need.
See the [Firecracker kernel docs](https://github.com/firecracker-microvm/firecracker/blob/main/docs/rootfs-and-kernel-setup.md).

## 3. Build Root Filesystem

The rootfs must contain an init process that reads the `BB_CMD_B64` parameter
from `/proc/cmdline`, base64-decodes it, and executes it. Blackbeard injects
the tool command via base64-encoded kernel boot args to prevent injection
attacks through spaces or shell metacharacters.

### Minimal rootfs with Alpine

```bash
# Create a 200MB ext4 image
dd if=/dev/zero of=/opt/firecracker/rootfs.ext4 bs=1M count=200
mkfs.ext4 /opt/firecracker/rootfs.ext4

# Mount and populate
mkdir -p /tmp/rootfs-mount
sudo mount /opt/firecracker/rootfs.ext4 /tmp/rootfs-mount

# Bootstrap Alpine
sudo apk -X https://dl-cdn.alpinelinux.org/alpine/latest-stable/main \
  -U --allow-untrusted --root /tmp/rootfs-mount --initdb add \
  alpine-base python3 py3-pip bash

# Create the init script that Blackbeard expects
sudo tee /tmp/rootfs-mount/init << 'INIT_EOF'
#!/bin/bash
# Parse BB_CMD_B64 from kernel command line (base64-encoded to prevent
# boot-arg injection via spaces or shell metacharacters in the command).
BB_CMD_B64=$(cat /proc/cmdline | tr ' ' '\n' | grep '^BB_CMD_B64=' | cut -d= -f2-)

# Parse BB_ENV_B64_* variables (base64-encoded values)
for param in $(cat /proc/cmdline | tr ' ' '\n' | grep '^BB_ENV_B64_'); do
    key=$(echo "$param" | sed 's/^BB_ENV_B64_//' | cut -d= -f1)
    value=$(echo "$param" | cut -d= -f2- | base64 -d)
    export "$key=$value"
done

# Decode and execute the command
if [ -n "$BB_CMD_B64" ]; then
    BB_CMD=$(echo "$BB_CMD_B64" | base64 -d)
    eval "$BB_CMD"
    EXIT_CODE=$?
else
    echo "No BB_CMD_B64 found in kernel command line" >&2
    EXIT_CODE=1
fi

# Shut down the VM
echo "$EXIT_CODE" > /dev/console
poweroff -f
INIT_EOF
sudo chmod +x /tmp/rootfs-mount/init

sudo umount /tmp/rootfs-mount
```

## 4. Configure Environment Variables

Set these in your `.env` file or environment:

```bash
# Path to the firecracker binary (default: "firecracker" on PATH)
FIRECRACKER_BIN=firecracker

# Path to the kernel image (required for Firecracker)
FIRECRACKER_KERNEL=/opt/firecracker/vmlinux.bin

# Path to the root filesystem image (required for Firecracker)
FIRECRACKER_ROOTFS=/opt/firecracker/rootfs.ext4
```

When `FIRECRACKER_KERNEL` is set and the firecracker binary and `/dev/kvm`
are available, Blackbeard automatically uses Firecracker for the `microvm`
sandbox tier. Otherwise it falls back to libkrun.

## 5. Verify

Check that Firecracker is detected:

```bash
# In the backend directory
uv run python -m blackbeard.engine.sandbox.selector
```

```
firecracker available: True
selected microvm backend: firecracker
```

## Docker Deployments

When running Blackbeard in Docker, pass through KVM and mount the kernel
and rootfs images:

```yaml
services:
  api:
    # ...
    devices:
      - /dev/kvm:/dev/kvm
    volumes:
      - /opt/firecracker/vmlinux.bin:/opt/firecracker/vmlinux.bin:ro
      - /opt/firecracker/rootfs.ext4:/opt/firecracker/rootfs.ext4:ro
    environment:
      FIRECRACKER_KERNEL: /opt/firecracker/vmlinux.bin
      FIRECRACKER_ROOTFS: /opt/firecracker/rootfs.ext4
```

## Security Considerations

- The rootfs image is mounted **read-only** (`is_read_only: true`).
- **No network interfaces** are attached by default.
- Each VM gets its own kernel, so kernel exploits in the guest cannot
  affect other VMs or the host.
- VMs are destroyed after each execution (no state leakage).
- The `firecracker` process runs unprivileged (needs only `/dev/kvm` access).

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `FirecrackerRuntimeError: not found` | Binary not on PATH | Set `FIRECRACKER_BIN` to the full path |
| `FirecrackerConfigError: FIRECRACKER_KERNEL` | Kernel path not set | Set the env var to the vmlinux path |
| `is_firecracker_available() = False` | Missing `/dev/kvm` | Enable KVM in BIOS/hypervisor; add user to `kvm` group |
| `FirecrackerTimeoutError` | VM too slow or hung | Increase timeout; check rootfs init script |
| Falls back to libkrun | Firecracker not configured | Set `FIRECRACKER_KERNEL` and `FIRECRACKER_ROOTFS` |

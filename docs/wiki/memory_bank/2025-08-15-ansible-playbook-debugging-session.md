# Ansible Playbook Debugging Session - 2025-08-15

## Summary
This document outlines a comprehensive debugging session that resolved a cascading series of failures in the Ansible deployment playbook. The root cause of the initial instability was traced to faulty hardware (a PoE network port), which was causing filesystem corruption on the `anakin.local` node. Subsequent investigation revealed and corrected multiple latent bugs in the Ansible playbooks.

## Issues and Resolutions

### 1. Initial Node Instability and Filesystem Corruption
- **Symptom:** The `anakin.local` node was frequently going down, and its root filesystem was mounting as read-only (`ro`). The node also required an SD card to boot despite having its rootfs on an NVMe drive.
- **Investigation:**
  - Confirmed the Pi's EEPROM bootloader was not configured to prioritize the NVMe drive.
  - Identified that running the `wipe_k3s_cluster.yml` playbook was making the node unbootable, suggesting a destructive operation was corrupting the disk.
- **Resolution:**
  - The primary root cause was discovered to be a faulty PoE port on the network switch, which was providing unstable power to the node. Moving the node to a different port resolved the instability.
  - As a preventative measure, a dangerous `sgdisk --zap-all` command, which was likely corrupting the disk's partition table, was commented out from the `wipe_k3s_cluster.yml` playbook.

### 2. Ansible: `iptables: not found`
- **Symptom:** The `wipe_k3s_cluster.yml` playbook failed on the `[Flush all iptables rules]` task with a "command not found" error on freshly imaged nodes.
- **Resolution:** An `ansible.builtin.apt` task was added to the beginning of the `wipe_k3s_cluster.yml` playbook to ensure the `iptables` package is installed on all nodes before it is used.

### 3. Ansible: `sudo: a password is required` on `localhost`
- **Symptom:** The `k3s_control_plane.yml` playbook failed on tasks delegated to `localhost` because it was unnecessarily trying to use `sudo`.
- **Resolution:** The `become: false` directive was added to all tasks delegated to `localhost` within the `k3s_control_plane.yml` playbook, preventing them from attempting privilege escalation on the Ansible controller machine.

### 4. Ansible: `Read-only file system: /root` on `localhost`
- **Symptom:** Even with `become: false`, a delegated task failed while trying to create `~/.kube/config`, with the path incorrectly resolving to `/root/.kube`.
- **Resolution:** The variable `{{ ansible_env.HOME }}` was replaced with `{{ lookup('env', 'HOME') }}` for all `localhost` tasks. This ensures the path correctly resolves to the home directory of the user running the playbook, not the `root` user.

### 5. Ansible: `env_vars is undefined`
- **Symptom:** The `rook_ceph_deploy_part2.yml` playbook failed because it was trying to use an undefined variable `env_vars` for `kubectl` commands.
- **Resolution:** All instances of `environment: "{{ env_vars }}"` were replaced with a correct environment block defining the `KUBECONFIG` variable: `environment: { KUBECONFIG: /etc/rancher/k3s/k3s.yaml }`.

### 6. Configuration Logic Enhancement
- **Symptom:** The user requested stricter control over which applications are deployed.
- **Resolution:** The logic in `config.yml` for all `enable_*` application flags was changed from `or` to `and`. An application is now only deployed if the global `cold_start_stage_3_install_applications` flag is true AND its specific `manual_install_*` flag is also true.

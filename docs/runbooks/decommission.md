# Decommissioning a group

1. Move every member to its new group:
   - agent-managed hosts: set `instance_group: <new>` in `agent-dynamic.conf`, then restart
     `nginx-agent` in place;
   - Flux-managed hosts: update the ConfigMap/Flux source and restart the agent in place. Do not
     recreate the pod.
2. Verify the new group has the members and the old group is empty.
3. Delete the group:

   ```bash
   curl --cacert certs/nim-ca.pem --resolve manager-server:443:$NIM_HOST \
     -u "$NIM_USER:$NIM_PASSWORD" -X DELETE \
     "$NIM_URL/api/platform/v1/instance-groups/<uid>"
   ```

   `412` means an agent still names the group. Move it, then retry.
4. Remove `groups/<group>/` and its `.nim/rendered.lock.json` entry.
5. `scripts/detect-groups.sh` skips a directory with no `group.yaml`, so a deleted directory can
   never enter a publish matrix. Add the change in a PR; the remaining groups are unaffected.

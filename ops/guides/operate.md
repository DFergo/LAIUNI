# Operating: updates, backups, secrets

## Updates
- Images: tag `latest` follows the main version; `sha-<commit>` pins one. Update (ask first): `compose action="pull" apply=true`, then `compose action="up" apply=true` in each folder (backend, frontends). Built-from-source backends: update the repo (`git pull` in the repo folder), then `compose up` (rebuilds).
- `t2-vps*` frontends run Watchtower: they update themselves at night.
- Update the repo too (`git pull`) so these guides and the MCP match the version.
- After updating: `status`, `test_smoke`.

## Backups
- All backend data is in the Docker volume (`hrdd-data`): configuration, knowledge base, sessions, reports.
- Configuration only (no conversations): `admin_api GET /admin/export/global` (counts as content when it includes sessions — ask) — or from the admin panel.
- Full backup of the volume (ask first; the backend keeps running):
  ```bash
  docker run --rm -v <project>_hrdd-data:/data -v ~/hrdd-backups:/backup alpine \
    tar czf /backup/hrdd-data-$(date +%F).tar.gz -C /data .
  ```
  (`docker volume ls` shows the exact volume name.) The archive contains sensitive data: keep it encrypted and access-controlled.

## Rotating the signing secret (no downtime)
1. On each frontend: `HRDD_BACKEND_SECRET_PREVIOUS` = current value, `HRDD_BACKEND_SECRET` = new value (`env_set`), restart.
2. On the backend: `HRDD_FRONTEND_SECRET` = new value, restart.
3. Later, empty `HRDD_BACKEND_SECRET_PREVIOUS` on the frontends.

## Admin password lost
Delete the admin hash in the volume and create a new account — see `docs/INSTALL.md` section 7.5. Ask first.

## Moving to another machine
Export (`/admin/export/global`, `/admin/export/frontend/{id}`) and import on the new backend, or copy the volume archive. Re-register frontends if the backend's view of their addresses changed.

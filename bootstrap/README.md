# Bootstrap

Three manifests register HuntReport with the sno hub so it gets continuously synced to the **sno-mini** spoke.

## Prerequisites (already done)

The following Vault paths are populated:

| Vault path | Purpose | Used by |
|---|---|---|
| `sno-mini/huntreport/quay-push-secret` | `.dockerconfigjson` for image pushes | Tekton `build-push` task |
| `sno-mini/openshift-gitops/repo-huntreport` | GitHub PAT (`password`) | `cronjob-poll` GitHub API auth |
| `sno-mini/argocd-agent/repo-huntreport` | git repo cred (`type`, `url`, `username`, `password`) | argocd agent on spoke |
| `sno/argocd-agent/repo-huntreport` | same data as above, mirrored to `sno/` scope | argocd on hub (3 namespaces) |

The PAT and Quay credentials are reused from `sno/openshift-gitops/repo-castreport` and `sno/castreport/quay-push-secret`. The Quay registry hostname was rewritten to `quay-server.apps.sno-mini.shanehomelab.com`.

## Apply order

The agent runs in autonomous mode, so the Application's source-of-truth is on the **spoke** (sno-mini); the hub holds a status mirror.

```bash
# 1. Hub: register the repo cred (3 namespaces × 1 ExternalSecret each)
oc login -u kubeadmin -p "$(cat ~/Documents/SNO/kubeadmin)" \
  --server=https://api.sno.shanehomelab.com:6443
oc apply -f bootstrap/repo-cred-hub.yaml

# 2. Spoke: register the repo cred AND the Application
oc login -u kubeadmin -p "$(cat ~/Documents/SNO-MINI/kubeadmin)" \
  --server=https://api.sno-mini.shanehomelab.com:6443
oc apply -f bootstrap/repo-cred-spoke.yaml
oc apply -f bootstrap/argocd-application.yaml

# 3. Watch sync (either on the spoke directly or via the hub mirror)
oc -n argocd-agent get application huntreport -w
# or, on the hub:
#   oc -n argocd-agent-sno-mini get application huntreport -w
```

Once `Synced` and `Healthy`, the app is reachable on sno-mini at:

```
https://huntreport-huntreport.apps.sno-mini.shanehomelab.com
```

## What gets created on sno-mini

Everything under `openshift/` of this repo, in the `huntreport` namespace:

- **Deployment / Service / Route** — the FastAPI app on port 8080
- **Pipelines** — `huntreport-prod` (main → `:latest` + `:prod-N`) and `huntreport-dev` (any branch → `:dev-<branch>` with branch-specific Deployment/Service/Route)
- **CronJob** — polls GitHub every 2 minutes, triggers the right pipeline on new commits, and reaps resources for deleted branches
- **ExternalSecrets** — pulls Quay push credentials and the GitHub PAT from Vault via the `vault-sno-mini` ClusterSecretStore

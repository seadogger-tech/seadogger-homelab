#!/usr/bin/env python3
"""
K8up Backup Manager - Simple web UI for viewing and restoring backups
Single-file Flask app with embedded HTML
"""
from flask import Flask, render_template_string, request, jsonify
from kubernetes import client, config
from datetime import datetime
import os
import time

app = Flask(__name__)

# Load Kubernetes config
try:
    config.load_incluster_config()
except:
    config.load_kube_config()

custom_api = client.CustomObjectsApi()
core_api = client.CoreV1Api()
apps_api = client.AppsV1Api()

NAMESPACES = ["nextcloud", "n8n", "jellyfin"]

PVC_MAP = {
    "n8n": "n8n-main-persistence",
    "nextcloud": "nextcloud-nextcloud",
    "jellyfin": "jellyfin-config"
}

# Store original replica counts during restore
REPLICA_COUNT_STORE = {}

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Backup Manager - SeaDogger Homelab</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, system-ui, Arial, sans-serif;
            background: linear-gradient(135deg, #0b2533 0%, #0e2e40 100%);
            color: #3A83B9;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { color: #38bdf8; margin-bottom: 30px; text-align: center; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; border-bottom: 2px solid rgba(255,255,255,0.1); }
        .tab {
            padding: 12px 24px; cursor: pointer; border: none; background: rgba(255,255,255,0.05);
            color: #8fbcd4; font-size: 16px; border-radius: 8px 8px 0 0; transition: all 0.2s;
        }
        .tab.active { background: rgba(56, 189, 248, 0.2); color: #38bdf8; font-weight: bold; }
        .tab:hover { background: rgba(255,255,255,0.1); }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        table { width: 100%; border-collapse: collapse; background: rgba(255,255,255,0.03); border-radius: 8px; overflow: hidden; }
        th { background: rgba(56, 189, 248, 0.1); padding: 12px; text-align: left; color: #38bdf8; font-weight: 600; }
        td { padding: 12px; border-top: 1px solid rgba(255,255,255,0.05); }
        tr:hover { background: rgba(255,255,255,0.05); }
        .restore-btn {
            background: #22c55e; color: white; border: none; padding: 8px 16px;
            border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.2s;
        }
        .restore-btn:hover { background: #16a34a; transform: translateY(-1px); }
        .restore-btn:active { transform: translateY(0); }
        .status { padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .status-success { background: rgba(34, 197, 94, 0.2); color: #22c55e; }
        .status-running { background: rgba(59, 130, 246, 0.2); color: #3b82f6; }
        .status-failed { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
        .alert { padding: 12px; margin: 10px 0; border-radius: 6px; background: rgba(234, 179, 8, 0.1); color: #eab308; border-left: 4px solid #eab308; }
        .loading { text-align: center; padding: 40px; color: #8fbcd4; }
        .empty { text-align: center; padding: 40px; color: #8fbcd4; font-style: italic; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🗄️ Backup Manager</h1>

        <div class="tabs">
            {% for ns in namespaces %}
            <button class="tab {% if loop.first %}active{% endif %}" onclick="showTab('{{ns}}')">{{ns | capitalize}}</button>
            {% endfor %}
        </div>

        {% for ns in namespaces %}
        <div id="{{ns}}" class="tab-content {% if loop.first %}active{% endif %}">
            <div class="alert">
                ⚠️ <strong>Warning:</strong> Restoring will overwrite current data in {{ns}}. The application will be automatically stopped during restore.
            </div>

            <div id="{{ns}}-status"></div>

            <table>
                <thead>
                    <tr>
                        <th>Snapshot ID</th>
                        <th>Date</th>
                        <th>Paths</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody id="{{ns}}-snapshots">
                    <tr><td colspan="4" class="loading">Loading snapshots...</td></tr>
                </tbody>
            </table>
        </div>
        {% endfor %}
    </div>

    <script>
        function showTab(namespace) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById(namespace).classList.add('active');
        }

        async function loadSnapshots(namespace) {
            try {
                const response = await fetch(`/api/snapshots/${namespace}`);
                const snapshots = await response.json();
                const tbody = document.getElementById(`${namespace}-snapshots`);

                if (snapshots.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" class="empty">No backups found</td></tr>';
                    return;
                }

                tbody.innerHTML = snapshots.map(snap => `
                    <tr>
                        <td><code>${snap.id}</code></td>
                        <td>${new Date(snap.date).toLocaleString()}</td>
                        <td>${snap.paths.join(', ')}</td>
                        <td>
                            <button class="restore-btn" onclick="restore('${namespace}', '${snap.id}')">
                                🔄 Restore
                            </button>
                        </td>
                    </tr>
                `).join('');
            } catch (error) {
                document.getElementById(`${namespace}-snapshots`).innerHTML =
                    `<tr><td colspan="4" style="color: #ef4444;">Error: ${error.message}</td></tr>`;
            }
        }

        async function restore(namespace, snapshotId) {
            if (!confirm(`Are you sure you want to restore ${namespace} from snapshot ${snapshotId}?\n\nThis will:\n1. Pause ArgoCD auto-sync\n2. Stop ${namespace}\n3. Overwrite current data\n4. Restart ${namespace}\n5. Re-enable ArgoCD auto-sync\n\nThis cannot be undone!`)) {
                return;
            }

            const statusDiv = document.getElementById(`${namespace}-status`);
            statusDiv.innerHTML = '<div class="alert">⏳ Step 1/5: Pausing ArgoCD auto-sync...</div>';

            // Start the restore (this will take a while)
            fetch(`/api/restore/${namespace}/${snapshotId}`, { method: 'POST' })
                .then(response => response.json())
                .then(result => {
                    if (result.restore_name) {
                        // Poll for status
                        pollRestoreStatus(namespace, result.restore_name);
                    } else {
                        statusDiv.innerHTML = `<div class="alert" style="background: rgba(239, 68, 68, 0.1); color: #ef4444; border-color: #ef4444;">
                            ❌ Restore failed: ${result.detail || 'Unknown error'}
                        </div>`;
                    }
                })
                .catch(error => {
                    statusDiv.innerHTML = `<div class="alert" style="background: rgba(239, 68, 68, 0.1); color: #ef4444; border-color: #ef4444;">
                        ❌ Error: ${error.message}
                    </div>`;
                });

            // Start showing progress immediately
            setTimeout(() => {
                statusDiv.innerHTML = '<div class="alert">⏳ Step 2/5: Scaling down deployment and waiting for pods to terminate...</div>';
            }, 2000);

            setTimeout(() => {
                statusDiv.innerHTML = '<div class="alert">⏳ Step 3/5: Creating restore job...</div>';
            }, 10000);
        }

        async function pollRestoreStatus(namespace, restoreName) {
            const maxAttempts = 60; // 5 minutes
            let attempts = 0;
            const statusDiv = document.getElementById(`${namespace}-status`);

            statusDiv.innerHTML = '<div class="alert">⏳ Step 4/5: Restoring data from S3 backup...</div>';

            const interval = setInterval(async () => {
                attempts++;
                try {
                    const response = await fetch(`/api/restore/${namespace}/${restoreName}/status`);
                    const status = await response.json();

                    if (status.started && !status.finished) {
                        statusDiv.innerHTML = '<div class="alert">⏳ Step 4/5: Restoring data from S3 backup... (in progress)</div>';
                    }

                    if (status.finished) {
                        clearInterval(interval);
                        const succeeded = status.conditions?.some(c => c.type === 'Completed' && c.status === 'True');

                        if (succeeded) {
                            statusDiv.innerHTML = '<div class="alert">⏳ Step 5/5: Restarting application and re-enabling ArgoCD...</div>';
                            setTimeout(() => {
                                statusDiv.innerHTML = `<div class="alert" style="background: rgba(34, 197, 94, 0.1); color: #22c55e; border-color: #22c55e;">
                                    ✅ Restore completed successfully! ${namespace} has been restarted with restored data.
                                </div>`;
                            }, 3000);
                        } else {
                            statusDiv.innerHTML = `<div class="alert" style="background: rgba(239, 68, 68, 0.1); color: #ef4444; border-color: #ef4444;">
                                ❌ Restore failed. Check logs: <code>kubectl logs -n ${namespace} -l k8up.io/owned-by=restore_${restoreName}</code>
                            </div>`;
                        }
                    }

                    if (attempts >= maxAttempts) {
                        clearInterval(interval);
                        statusDiv.innerHTML = `<div class="alert" style="background: rgba(239, 68, 68, 0.1); color: #ef4444; border-color: #ef4444;">
                            ⚠️ Restore status check timed out. Check manually: <code>kubectl get restore ${restoreName} -n ${namespace}</code>
                        </div>`;
                    }
                } catch (error) {
                    console.error('Status poll error:', error);
                }
            }, 5000); // Check every 5 seconds
        }

        // Load snapshots for all namespaces on page load
        ['nextcloud', 'n8n', 'jellyfin'].forEach(ns => loadSnapshots(ns));
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, namespaces=NAMESPACES)

@app.route('/api/snapshots/<namespace>')
def get_snapshots(namespace):
    try:
        snapshots = custom_api.list_namespaced_custom_object(
            group="k8up.io",
            version="v1",
            namespace=namespace,
            plural="snapshots"
        )

        result = []
        for snap in snapshots.get("items", []):
            result.append({
                "id": snap["metadata"]["name"],
                "date": snap["spec"].get("date", "Unknown"),
                "paths": snap["spec"].get("paths", []),
            })

        result.sort(key=lambda x: x["date"], reverse=True)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/restore/<namespace>/<snapshot_id>', methods=['POST'])
def create_restore(namespace, snapshot_id):
    try:
        # Get current replica count before scaling down
        original_replicas = 1  # Default fallback
        try:
            deployment = apps_api.read_namespaced_deployment(name=namespace, namespace=namespace)
            original_replicas = deployment.spec.replicas or 1

            # Pause ArgoCD auto-sync to prevent it from reverting our changes
            try:
                custom_api.patch_namespaced_custom_object(
                    group="argoproj.io",
                    version="v1alpha1",
                    namespace="argocd",
                    plural="applications",
                    name=namespace,
                    body={"spec": {"syncPolicy": {"automated": None}}}
                )
            except:
                pass  # ArgoCD app might not exist

            # Scale deployment to 0
            apps_api.patch_namespaced_deployment_scale(
                name=namespace,
                namespace=namespace,
                body={"spec": {"replicas": 0}}
            )

            # Wait for pods to terminate (max 60 seconds)
            max_wait = 60
            wait_interval = 2
            elapsed = 0

            while elapsed < max_wait:
                pods = core_api.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=f"app.kubernetes.io/name={namespace}"
                )

                # Check if all pods are gone
                if len(pods.items) == 0:
                    break

                # Check if all remaining pods are terminating
                all_terminating = all(pod.metadata.deletion_timestamp is not None for pod in pods.items)
                if all_terminating:
                    time.sleep(wait_interval)
                    elapsed += wait_interval
                else:
                    # Some pods still running
                    time.sleep(wait_interval)
                    elapsed += wait_interval

            # Additional 2 second buffer to ensure PVC detachment
            time.sleep(2)

        except client.exceptions.ApiException as e:
            if e.status != 404:
                raise
            # Deployment doesn't exist, proceed anyway

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        restore_name = f"{namespace}-restore-{timestamp}"

        # Store original replica count for this restore
        REPLICA_COUNT_STORE[restore_name] = original_replicas

        restore_spec = {
            "apiVersion": "k8up.io/v1",
            "kind": "Restore",
            "metadata": {"name": restore_name, "namespace": namespace},
            "spec": {
                "snapshot": snapshot_id,
                "backend": {
                    "repoPasswordSecretRef": {"name": "k8up-s3-credentials", "key": "RESTIC_PASSWORD"},
                    "s3": {
                        "endpoint": "https://s3.amazonaws.com",
                        "bucket": "seadogger-homelab-backup",
                        "accessKeyIDSecretRef": {"name": "k8up-s3-credentials", "key": "AWS_ACCESS_KEY_ID"},
                        "secretAccessKeySecretRef": {"name": "k8up-s3-credentials", "key": "AWS_SECRET_ACCESS_KEY"}
                    }
                },
                "restoreMethod": {"folder": {"claimName": PVC_MAP[namespace]}},
                "podSecurityContext": {"runAsUser": 0, "fsGroup": 0}
            }
        }

        custom_api.create_namespaced_custom_object(
            group="k8up.io",
            version="v1",
            namespace=namespace,
            plural="restores",
            body=restore_spec
        )

        return jsonify({"status": "created", "restore_name": restore_name, "namespace": namespace})
    except Exception as e:
        return jsonify({"detail": str(e)}), 500

@app.route('/api/restore/<namespace>/<restore_name>/status')
def get_restore_status(namespace, restore_name):
    try:
        restore = custom_api.get_namespaced_custom_object(
            group="k8up.io",
            version="v1",
            namespace=namespace,
            plural="restores",
            name=restore_name
        )

        status = restore.get("status", {})

        # If restore finished successfully, restart the application
        if status.get("finished") and any(c.get("type") == "Completed" and c.get("status") == "True"
                                          for c in status.get("conditions", [])):
            try:
                # Restore to original replica count, not hardcoded to 1
                original_replicas = REPLICA_COUNT_STORE.get(restore_name, 1)

                apps_api.patch_namespaced_deployment_scale(
                    name=namespace,
                    namespace=namespace,
                    body={"spec": {"replicas": original_replicas}}
                )

                # Re-enable ArgoCD auto-sync
                try:
                    custom_api.patch_namespaced_custom_object(
                        group="argoproj.io",
                        version="v1alpha1",
                        namespace="argocd",
                        plural="applications",
                        name=namespace,
                        body={"spec": {"syncPolicy": {"automated": {"prune": True, "selfHeal": True}}}}
                    )
                except:
                    pass

                # Clean up the stored replica count
                if restore_name in REPLICA_COUNT_STORE:
                    del REPLICA_COUNT_STORE[restore_name]
            except:
                pass

        return jsonify({
            "name": restore_name,
            "started": status.get("started", False),
            "finished": status.get("finished", False),
            "conditions": status.get("conditions", [])
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)

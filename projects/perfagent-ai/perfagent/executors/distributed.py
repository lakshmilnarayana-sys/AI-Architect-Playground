from __future__ import annotations

import subprocess
import shlex
import yaml
from pathlib import Path
from typing import Any

from perfagent.collectors.distributed_results import write_merged_worker_results
from perfagent.core.artifacts import write_json


def build_distributed_plan(
    *,
    engine: str,
    service_name: str,
    workers: int,
    output_dir: Path,
    compose_service: str = "perfagent",
) -> dict[str, Any]:
    workers = max(1, int(workers))
    output = str(output_dir)
    commands = [
        f"docker compose build {compose_service}",
        (
            f"docker compose run --rm --scale {compose_service}={workers} {compose_service} evaluate "
            f"--config ./examples/sample-config.yaml --engine {engine} --output {output}"
        ),
    ]
    return {
        "mode": "distributed-container",
        "engine": engine,
        "service_name": service_name,
        "workers": workers,
        "compose_service": compose_service,
        "output_dir": output,
        "commands": commands,
        "warnings": [
            "MVP distributed mode is a plan generator; coordinated result merge is still required for multi-worker execution."
        ],
    }


def build_distributed_coordinator_plan(
    *,
    engine: str,
    service_name: str,
    workers: int,
    output_dir: Path,
    base_config: str = "./examples/sample-config.yaml",
    compose_service: str = "perfagent",
    backend: str = "local",
    compose_file: str = "docker-compose.yml",
    project_name: str | None = None,
    namespace: str = "default",
    image: str = "perfagent-ai:latest",
    artifact_pvc: str | None = None,
    retry_limit: int = 1,
) -> dict[str, Any]:
    workers = max(1, int(workers))
    worker_specs = []
    output_dir = Path(output_dir)
    project_name = project_name or f"perfagent-{service_name}".replace("_", "-")
    compose_prefix = f"docker compose -f {compose_file} -p {project_name}" if backend == "docker-compose" else "docker compose"
    for index in range(workers):
        worker_id = f"worker-{index + 1}"
        worker_output = output_dir / worker_id
        summary_path = worker_output / "raw" / "k6_summary.json"
        environment = {
            "PERFAGENT_WORKER_ID": worker_id,
            "PERFAGENT_SERVICE_NAME": service_name,
            "PERFAGENT_ENGINE": engine,
        }
        env_args = " ".join(f"-e {key}={value}" for key, value in environment.items())
        if backend == "kubernetes":
            job_name = _kubernetes_job_name(service_name, worker_id)
            remote_output = f"/workspace/artifacts/{worker_id}" if artifact_pvc else f"/workspace/{worker_id}"
            manifest = _kubernetes_worker_manifest(
                job_name=job_name,
                namespace=namespace,
                image=image,
                worker_id=worker_id,
                service_name=service_name,
                engine=engine,
                base_config=base_config,
                output_dir=remote_output,
                artifact_pvc=artifact_pvc,
                retry_limit=retry_limit,
            )
            manifest_path = output_dir / f"{job_name}.yaml"
            worker_specs.append(
                {
                    "worker_id": worker_id,
                    "kind": "Job",
                    "job_name": job_name,
                    "output_dir": str(worker_output),
                    "summary_path": str(summary_path),
                    "environment": environment,
                    "manifest_path": str(manifest_path),
                    "manifest": manifest,
                    "command": f"kubectl -n {namespace} apply -f {manifest_path}",
                    "wait_command": f"kubectl -n {namespace} wait --for=condition=complete job/{job_name} --timeout=30m",
                    "artifact_command": f"kubectl -n {namespace} cp job/{job_name}:{remote_output} {worker_output}",
                }
            )
        else:
            worker_specs.append(
                {
                    "worker_id": worker_id,
                    "output_dir": str(worker_output),
                    "summary_path": str(summary_path),
                    "environment": environment,
                    "command": (
                        f"{compose_prefix} run --rm {env_args} {compose_service} evaluate "
                        f"--config {base_config} --service-name {service_name} --engine {engine} "
                        f"--output {worker_output}"
                    ),
                }
            )
    merge_command = (
        "perfagent distributed merge "
        + " ".join(f"--worker-summary {worker['summary_path']}" for worker in worker_specs)
        + f" --output-dir {output_dir / 'merged'}"
    )
    return {
        "mode": "distributed-coordinator",
        "backend": backend,
        "engine": engine,
        "service_name": service_name,
        "workers": workers,
        "compose_service": compose_service,
        "compose_file": compose_file,
        "project_name": project_name,
        "namespace": namespace if backend == "kubernetes" else None,
        "image": image if backend == "kubernetes" else None,
        "artifact_pvc": artifact_pvc,
        "retry_limit": retry_limit,
        "output_dir": str(output_dir),
        "lifecycle": _distributed_lifecycle(backend, compose_prefix, compose_service, namespace, base_config, worker_specs),
        "worker_specs": worker_specs,
        "merge_command": merge_command,
        "warnings": [
            "Coordinator plan is deterministic; use --execute to run worker lifecycle commands.",
            "Use distributed merge after worker summaries are available.",
        ],
    }


def _distributed_lifecycle(
    backend: str,
    compose_prefix: str,
    compose_service: str,
    namespace: str,
    base_config: str,
    worker_specs: list[dict[str, Any]],
) -> dict[str, list[str]]:
    if backend == "docker-compose":
        return {"setup": [f"{compose_prefix} build {compose_service}"], "teardown": [f"{compose_prefix} down --remove-orphans"]}
    if backend == "kubernetes":
        return {
            "setup": [f"kubectl -n {namespace} create configmap perfagent-config --from-file=config={base_config} --dry-run=client -o yaml | kubectl apply -f -"],
            "teardown": [f"kubectl -n {namespace} delete job {' '.join(worker['job_name'] for worker in worker_specs)} --ignore-not-found=true"],
        }
    return {"setup": [], "teardown": []}


def _kubernetes_job_name(service_name: str, worker_id: str) -> str:
    safe_service = "".join(char if char.isalnum() or char == "-" else "-" for char in service_name.lower()).strip("-")
    return f"perfagent-{safe_service}-{worker_id}"


def _kubernetes_worker_manifest(
    *,
    job_name: str,
    namespace: str,
    image: str,
    worker_id: str,
    service_name: str,
    engine: str,
    base_config: str,
    output_dir: str,
    artifact_pvc: str | None,
    retry_limit: int,
) -> dict[str, Any]:
    volumes = [{"name": "config", "configMap": {"name": "perfagent-config"}}]
    mounts = [{"name": "config", "mountPath": "/workspace/config"}]
    if artifact_pvc:
        volumes.append({"name": "artifacts", "persistentVolumeClaim": {"claimName": artifact_pvc}})
        mounts.append({"name": "artifacts", "mountPath": "/workspace/artifacts"})
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": job_name, "namespace": namespace, "labels": {"app": "perfagent", "worker": worker_id}},
        "spec": {
            "backoffLimit": int(retry_limit),
            "template": {
                "metadata": {"labels": {"app": "perfagent", "worker": worker_id}},
                "spec": {
                    "restartPolicy": "Never",
                    "volumes": volumes,
                    "containers": [
                        {
                            "name": "perfagent",
                            "image": image,
                            "env": [
                                {"name": "PERFAGENT_WORKER_ID", "value": worker_id},
                                {"name": "PERFAGENT_SERVICE_NAME", "value": service_name},
                                {"name": "PERFAGENT_ENGINE", "value": engine},
                            ],
                            "volumeMounts": mounts,
                            "args": [
                                "evaluate",
                                "--config",
                                "/workspace/config/config",
                                "--service-name",
                                service_name,
                                "--engine",
                                engine,
                                "--output",
                                output_dir,
                            ],
                        }
                    ],
                },
            },
        },
    }


def run_distributed_coordinator(plan: dict[str, Any], *, output_path: Path | None = None) -> dict[str, Any]:
    worker_results: list[dict[str, Any]] = []
    lifecycle_results: list[dict[str, Any]] = []
    _write_worker_manifests(plan)
    for command in plan.get("lifecycle", {}).get("setup", []):
        setup_result = _run_command(command)
        lifecycle_results.append(
            {
                "phase": "setup",
                "command": command,
                "exit_code": setup_result.returncode,
                "stdout": setup_result.stdout[-4000:],
                "stderr": setup_result.stderr[-4000:],
            }
        )
        if setup_result.returncode != 0:
            result = {
                "mode": "distributed-coordinator-execution",
                "plan": plan,
                "lifecycle": lifecycle_results,
                "workers": [],
                "merged": None,
                "success": False,
                "warnings": ["Distributed setup failed; workers were not started."],
            }
            if output_path:
                write_json(output_path, result)
            return result
    for worker in plan.get("worker_specs", []):
        result = _run_command(worker["command"])
        wait_result = None
        artifact_result = None
        if result.returncode == 0 and worker.get("wait_command"):
            wait_result = _run_command(worker["wait_command"])
        if (wait_result is None or wait_result.returncode == 0) and worker.get("artifact_command"):
            artifact_result = _run_command(worker["artifact_command"])
        worker_results.append(
            {
                "worker_id": worker.get("worker_id"),
                "command": worker.get("command"),
                "exit_code": result.returncode,
                "wait_command": worker.get("wait_command"),
                "wait_exit_code": wait_result.returncode if wait_result else None,
                "artifact_command": worker.get("artifact_command"),
                "artifact_exit_code": artifact_result.returncode if artifact_result else None,
                "summary_path": worker.get("summary_path"),
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            }
        )
    summary_paths = [Path(worker["summary_path"]) for worker in plan.get("worker_specs", []) if Path(worker["summary_path"]).exists()]
    merged: dict[str, Any] | None = None
    if summary_paths:
        merged = write_merged_worker_results(
            summary_paths,
            summary_path=Path(plan["output_dir"]) / "merged" / "raw" / "merged_summary.json",
            aligned_path=Path(plan["output_dir"]) / "merged" / "processed" / "aligned_timeseries.csv",
        )
    for command in plan.get("lifecycle", {}).get("teardown", []):
        teardown_result = _run_command(command)
        lifecycle_results.append(
            {
                "phase": "teardown",
                "command": command,
                "exit_code": teardown_result.returncode,
                "stdout": teardown_result.stdout[-4000:],
                "stderr": teardown_result.stderr[-4000:],
            }
        )
    result = {
        "mode": "distributed-coordinator-execution",
        "plan": plan,
        "lifecycle": lifecycle_results,
        "workers": worker_results,
        "merged": merged,
        "success": all(item["exit_code"] == 0 for item in lifecycle_results)
        and all(worker["exit_code"] == 0 and (worker.get("wait_exit_code") in {None, 0}) and (worker.get("artifact_exit_code") in {None, 0}) for worker in worker_results)
        and bool(merged),
        "warnings": [] if merged else ["No worker summaries were available to merge."],
    }
    if output_path:
        write_json(output_path, result)
    return result


def _write_worker_manifests(plan: dict[str, Any]) -> None:
    for worker in plan.get("worker_specs", []):
        manifest = worker.get("manifest")
        manifest_path = worker.get("manifest_path")
        if manifest and manifest_path:
            path = Path(manifest_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump(manifest, sort_keys=False))


def _run_command(command: str) -> subprocess.CompletedProcess[str]:
    if "|" in command:
        return subprocess.run(command, shell=True, text=True, capture_output=True, check=False)
    return subprocess.run(shlex.split(command), text=True, capture_output=True, check=False)

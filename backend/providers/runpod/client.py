"""RunPod API Client.

Handles authentication, pod discovery, lifecycle management,
and connection info retrieval for GPU workers.

RunPod uses a GraphQL API at https://api.runpod.io/graphql.

All secrets are read from environment variables — never hardcoded.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

RUNPOD_API_BASE = "https://api.runpod.io/graphql"
RUNPOD_REST_BASE = "https://api.runpod.io/v2"


class RunPodClientError(Exception):
    """Raised when RunPod API returns an error."""


class RunPodClient:
    """Client for the RunPod GPU cloud API.

    Mirrors the VastClient interface so it can be used interchangeably
    by the worker orchestrator and connection race system.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("RUNPOD_API_KEY", "")
        if not self.api_key:
            raise RunPodClientError("No RunPod API key found. Set RUNPOD_API_KEY in .env")
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # ─── GraphQL Helper ───────────────────────────────────────────────────

    def _graphql(self, query: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL query against RunPod API."""
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            resp = httpx.post(
                RUNPOD_API_BASE,
                headers=self._headers,
                json=payload,
                timeout=30,
            )
        except httpx.HTTPError as e:
            raise RunPodClientError(f"Network error: {e}")

        if resp.status_code != 200:
            raise RunPodClientError(f"RunPod API error ({resp.status_code}): {resp.text}")

        data = resp.json()
        if "errors" in data:
            error_msg = data["errors"][0].get("message", "Unknown GraphQL error")
            raise RunPodClientError(f"GraphQL error: {error_msg}")

        return data.get("data", {})

    # ─── Authentication ───────────────────────────────────────────────────

    def validate_api_key(self) -> dict:
        """Validate the API key by fetching account info."""
        query = """
        query {
            myself {
                id
                email
                currentSpendPerHr
                machineQuota
                referralEarned
                signedTermsOfService
                clientBalance
            }
        }
        """
        data = self._graphql(query)
        myself = data.get("myself")
        if not myself:
            raise RunPodClientError("Failed to validate API key")
        return myself

    def get_balance(self) -> float:
        """Get current account credit balance."""
        info = self.validate_api_key()
        return float(info.get("clientBalance", info.get("creditBalance", 0)))

    # ─── GPU Types / Offers ───────────────────────────────────────────────

    def list_gpu_types(self) -> list[dict]:
        """List available GPU types on RunPod."""
        query = """
        query {
            gpuTypes {
                id
                displayName
                memoryInGb
                maxGpuCount
                communityPrice
                securePrice
                communitySpotPrice
                secureSpotPrice
            }
        }
        """
        data = self._graphql(query)
        return data.get("gpuTypes", [])

    def filter_gpu_types(
        self,
        gpu_name: str | None = None,
        min_vram_gb: float = 0,
        max_price_per_hour: float | None = None,
    ) -> list[dict]:
        """Filter GPU types by name, VRAM, and price."""
        max_price = max_price_per_hour or float(os.getenv("RUNPOD_MAX_PRICE_PER_HOUR", "99"))
        gpu_types = self.list_gpu_types()
        filtered = []
        for gpu in gpu_types:
            if gpu_name and gpu_name.lower() not in gpu.get("displayName", "").lower():
                continue
            if gpu.get("memoryInGb", 0) < min_vram_gb:
                continue
            # Use community price (cheapest) for filtering
            price = gpu.get("communityPrice") or gpu.get("securePrice") or 999
            if price > max_price:
                continue
            filtered.append(gpu)
        return filtered

    # ─── Pod Lifecycle ────────────────────────────────────────────────────

    def launch_pod(
        self,
        gpu_type_id: str,
        image: str | None = None,
        disk_gb: int | None = None,
        volume_gb: int | None = None,
        name: str | None = None,
        env: dict[str, str] | None = None,
        cloud_type: str = "COMMUNITY",
        ports: str | None = None,
    ) -> dict:
        """Launch a new GPU pod.

        Args:
            gpu_type_id: GPU type ID from list_gpu_types (e.g. "NVIDIA RTX 4090")
            image: Docker image (default: pytorch/pytorch)
            disk_gb: Container disk size
            volume_gb: Persistent volume size
            name: Pod name
            env: Environment variables
            cloud_type: COMMUNITY or SECURE
            ports: Port mappings (e.g. "8188/http,22/tcp")
        """
        img = image or os.getenv(
            "RUNPOD_DEFAULT_IMAGE",
            "runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04",
        )
        disk = disk_gb or int(os.getenv("RUNPOD_DISK_GB", "80"))
        vol = volume_gb or int(os.getenv("RUNPOD_VOLUME_GB", "50"))
        pod_name = name or f"ai-studio-worker-{int(time.time())}"
        port_str = ports or "8188/http,22/tcp"

        # Build environment variables
        env_list = []
        if env:
            for k, v in env.items():
                env_list.append({"key": k, "value": v})

        query = """
        mutation ($input: PodFindAndDeployOnDemandInput!) {
            podFindAndDeployOnDemand(input: $input) {
                id
                name
                runtime {
                    uptimeInSeconds
                    ports {
                        ip
                        isIpPublic
                        privatePort
                        publicPort
                        type
                    }
                    gpus {
                        id
                        gpuUtilPercent
                        memoryUtilPercent
                    }
                }
                machine {
                    gpuDisplayName
                }
            }
        }
        """
        variables = {
            "input": {
                "name": pod_name,
                "imageName": img,
                "gpuTypeId": gpu_type_id,
                "cloudType": cloud_type,
                "containerDiskInGb": disk,
                "volumeInGb": vol,
                "ports": port_str,
                "volumeMountPath": "/workspace",
                "env": env_list,
            }
        }

        data = self._graphql(query, variables)
        pod = data.get("podFindAndDeployOnDemand")
        if not pod:
            raise RunPodClientError("Failed to launch pod — no response data")
        return pod

    def get_pod(self, pod_id: str) -> dict:
        """Get pod details by ID."""
        query = """
        query ($podId: String!) {
            pod(input: { podId: $podId }) {
                id
                name
                desiredStatus
                runtime {
                    uptimeInSeconds
                    ports {
                        ip
                        isIpPublic
                        privatePort
                        publicPort
                        type
                    }
                    gpus {
                        id
                        gpuUtilPercent
                        memoryUtilPercent
                    }
                }
                machine {
                    gpuDisplayName
                    podHostId
                }
                costPerHr
                gpuCount
            }
        }
        """
        data = self._graphql(query, {"podId": pod_id})
        pod = data.get("pod")
        if not pod:
            raise RunPodClientError(f"Pod {pod_id} not found")
        return pod

    def get_pods(self) -> list[dict]:
        """List all current pods."""
        query = """
        query {
            myself {
                pods {
                    id
                    name
                    desiredStatus
                    runtime {
                        uptimeInSeconds
                        ports {
                            ip
                            isIpPublic
                            privatePort
                            publicPort
                            type
                        }
                    }
                    machine {
                        gpuDisplayName
                        podHostId
                    }
                    costPerHr
                    gpuCount
                }
            }
        }
        """
        data = self._graphql(query)
        myself = data.get("myself", {})
        return myself.get("pods", [])

    def stop_pod(self, pod_id: str) -> dict:
        """Stop (pause) a pod — preserves state, stops billing."""
        query = """
        mutation ($input: PodStopInput!) {
            podStop(input: $input) {
                id
                desiredStatus
            }
        }
        """
        data = self._graphql(query, {"input": {"podId": pod_id}})
        return data.get("podStop", {"id": pod_id, "status": "stopped"})

    def resume_pod(self, pod_id: str) -> dict:
        """Resume a stopped pod."""
        query = """
        mutation ($input: PodResumeInput!) {
            podResume(input: $input) {
                id
                desiredStatus
                costPerHr
            }
        }
        """
        data = self._graphql(query, {"input": {"podId": pod_id}})
        return data.get("podResume", {"id": pod_id, "status": "running"})

    def terminate_pod(self, pod_id: str) -> dict:
        """Permanently terminate and delete a pod."""
        query = """
        mutation ($input: PodTerminateInput!) {
            podTerminate(input: $input)
        }
        """
        self._graphql(query, {"input": {"podId": pod_id}})
        return {"status": "terminated", "pod_id": pod_id}

    # ─── Connection Info ──────────────────────────────────────────────────

    def get_connection_info(self, pod_id: str) -> dict:
        """Get SSH/HTTP connection info for a pod."""
        pod = self.get_pod(pod_id)
        runtime = pod.get("runtime") or {}
        ports = runtime.get("ports", [])

        ssh_port = None
        ssh_host = None
        comfyui_port = None

        for port in ports:
            private = port.get("privatePort")
            public = port.get("publicPort")
            ip = port.get("ip", "")

            if private == 22:
                ssh_port = public
                ssh_host = ip
            elif private == 8188:
                comfyui_port = public
                if not ssh_host:
                    ssh_host = ip

        gpu_name = pod.get("machine", {}).get("gpuDisplayName", "")

        return {
            "pod_id": pod_id,
            "instance_id": pod_id,  # Compatibility with VastClient interface
            "public_ip": ssh_host or "",
            "ssh_host": ssh_host or "",
            "ssh_port": ssh_port,
            "comfyui_port": comfyui_port,
            "comfyui_url": f"http://{ssh_host}:{comfyui_port}"
            if comfyui_port and ssh_host
            else None,
            "status": pod.get("desiredStatus", "unknown"),
            "gpu_name": gpu_name,
            "cost_per_hr": pod.get("costPerHr", 0),
        }

    def wait_for_pod(self, pod_id: str, timeout: int = 300, poll_interval: int = 10) -> dict:
        """Wait for a pod to become running."""
        start = time.time()
        while time.time() - start < timeout:
            pod = self.get_pod(pod_id)
            status = pod.get("desiredStatus", "")
            runtime = pod.get("runtime")

            if status == "RUNNING" and runtime and runtime.get("ports"):
                return self.get_connection_info(pod_id)

            time.sleep(poll_interval)

        raise RunPodClientError(f"Pod {pod_id} did not start within {timeout}s")

    # ─── Status (mirrors VastClient pattern) ──────────────────────────────

    def get_status(self) -> dict:
        """Get comprehensive RunPod provider status.

        Returns a dict matching the format used by the /vast/status endpoint
        so the frontend can handle both providers uniformly.
        """
        try:
            account = self.validate_api_key()
            pods = self.get_pods()

            active_pods = [p for p in pods if p.get("desiredStatus") == "RUNNING"]
            paused_pods = [p for p in pods if p.get("desiredStatus") == "EXITED"]

            active_pod = active_pods[0] if active_pods else None
            instance_info = None
            if active_pod:
                gpu_name = active_pod.get("machine", {}).get("gpuDisplayName", "")
                instance_info = {
                    "id": active_pod.get("id"),
                    "gpu_name": gpu_name,
                    "price_per_hour": active_pod.get("costPerHr", 0),
                    "status": "running",
                    "name": active_pod.get("name", ""),
                }

            return {
                "provider": "runpod",
                "api_connected": True,
                "instance_active": len(active_pods) > 0,
                "instance_paused": len(paused_pods) > 0,
                "balance": float(account.get("clientBalance", account.get("creditBalance", 0))),
                "spend_per_hr": float(account.get("currentSpendPerHr", 0)),
                "instance_info": instance_info,
                "total_pods": len(pods),
                "active_pods": len(active_pods),
                "paused_pods": len(paused_pods),
            }
        except RunPodClientError as e:
            return {
                "provider": "runpod",
                "api_connected": False,
                "instance_active": False,
                "instance_paused": False,
                "balance": 0,
                "instance_info": None,
                "error": str(e),
            }

"""RunPod API Client.

Handles authentication, pod discovery, instance lifecycle,
and connection info retrieval for GPU workers on RunPod.

RunPod advantages over Vast.ai:
- Persistent volumes (models survive restarts)
- Faster boot (pre-built templates with ComfyUI)
- Network volumes for shared model storage
- Serverless endpoints (pay per inference, no idle cost)

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
    """Client for the RunPod GPU cloud API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("RUNPOD_API_KEY")
        if not self.api_key:
            raise RunPodClientError("No RunPod API key found. Set RUNPOD_API_KEY in .env")
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # ─── Authentication ───────────────────────────────────────────────────

    def validate_api_key(self) -> dict:
        """Validate the API key by fetching account info."""
        query = '{ myself { id email currentSpendPerHr } }'
        data = self._graphql(query)
        return data.get("myself", {})

    def get_balance(self) -> float:
        """Get current RunPod credit balance."""
        # Use the spending endpoint — RunPod doesn't expose credits in GraphQL anymore
        info = self.validate_api_key()
        return float(info.get("currentSpendPerHr", 0))

    # ─── GPU Types ────────────────────────────────────────────────────────

    def list_gpu_types(self) -> list[dict]:
        """List available GPU types and their pricing."""
        query = """
        {
            gpuTypes {
                id
                displayName
                memoryInGb
                secureCloud
                communityCloud
                lowestPrice(input: { gpuCount: 1 }) {
                    minimumBidPrice
                    uninterruptablePrice
                }
            }
        }
        """
        data = self._graphql(query)
        return data.get("gpuTypes", [])

    def filter_gpu_types(
        self,
        min_vram_gb: float = 0,
        max_price_per_hour: float | None = None,
        gpu_name: str | None = None,
    ) -> list[dict]:
        """Filter GPU types by VRAM and price."""
        max_price = max_price_per_hour or float(os.getenv("RUNPOD_MAX_PRICE", "2.0"))
        all_types = self.list_gpu_types()
        filtered = []
        for gpu in all_types:
            if gpu.get("memoryInGb", 0) < min_vram_gb:
                continue
            price_info = gpu.get("lowestPrice", {})
            price = price_info.get("uninterruptablePrice") or price_info.get("minimumBidPrice") or 999
            if price > max_price:
                continue
            if gpu_name and gpu_name.lower() not in gpu.get("displayName", "").lower():
                continue
            gpu["price_per_hour"] = price
            filtered.append(gpu)
        filtered.sort(key=lambda g: g.get("price_per_hour", 999))
        return filtered

    # ─── Pod Lifecycle ────────────────────────────────────────────────────

    def create_pod(
        self,
        name: str = "ai-studio-worker",
        gpu_type_id: str = "NVIDIA RTX 4090",
        image: str = "runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04",
        disk_gb: int = 80,
        volume_gb: int = 50,
        env: dict[str, str] | None = None,
        docker_args: str | None = None,
    ) -> dict:
        """Create a new GPU pod."""
        env_vars = env or {}
        env_str = ", ".join(
            f'{{ key: "{k}", value: "{v}" }}' for k, v in env_vars.items()
        )

        query = f"""
        mutation {{
            podFindAndDeployOnDemand(input: {{
                name: "{name}"
                imageName: "{image}"
                gpuTypeId: "{gpu_type_id}"
                cloudType: SECURE
                volumeInGb: {volume_gb}
                containerDiskInGb: {disk_gb}
                minVcpuCount: 2
                minMemoryInGb: 8
                ports: "8188/http,11434/http,7860/http,22/tcp"
                {f'env: [{env_str}]' if env_str else ''}
                {f'dockerArgs: "{docker_args}"' if docker_args else ''}
            }}) {{
                id
                name
                desiredStatus
                imageName
                machine {{
                    gpuDisplayName
                }}
                runtime {{
                    uptimeInSeconds
                    ports {{
                        ip
                        isIpPublic
                        privatePort
                        publicPort
                        type
                    }}
                }}
            }}
        }}
        """
        data = self._graphql(query)
        return data.get("podFindAndDeployOnDemand", {})

    def get_pod(self, pod_id: str) -> dict:
        """Get pod details."""
        query = f"""
        {{
            pod(input: {{ podId: "{pod_id}" }}) {{
                id
                name
                desiredStatus
                imageName
                machine {{
                    gpuDisplayName
                }}
                runtime {{
                    uptimeInSeconds
                    gpus {{
                        id
                        gpuUtilPercent
                        memoryUtilPercent
                    }}
                    ports {{
                        ip
                        isIpPublic
                        privatePort
                        publicPort
                        type
                    }}
                }}
                lastStatusChange
            }}
        }}
        """
        data = self._graphql(query)
        return data.get("pod", {})

    def get_pods(self) -> list[dict]:
        """List all current pods."""
        query = """
        {
            myself {
                pods {
                    id
                    name
                    desiredStatus
                    imageName
                    machine {
                        gpuDisplayName
                    }
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
                    lastStatusChange
                }
            }
        }
        """
        data = self._graphql(query)
        myself = data.get("myself", {})
        return myself.get("pods", [])

    def stop_pod(self, pod_id: str) -> dict:
        """Stop (pause) a pod. Pod state is preserved."""
        query = f"""
        mutation {{
            podStop(input: {{ podId: "{pod_id}" }}) {{
                id
                desiredStatus
            }}
        }}
        """
        data = self._graphql(query)
        return data.get("podStop", {})

    def resume_pod(self, pod_id: str) -> dict:
        """Resume a stopped pod."""
        query = f"""
        mutation {{
            podResume(input: {{ podId: "{pod_id}" }}) {{
                id
                desiredStatus
            }}
        }}
        """
        data = self._graphql(query)
        return data.get("podResume", {})

    def terminate_pod(self, pod_id: str) -> dict:
        """Permanently terminate a pod (destroys disk, keeps volume)."""
        query = f"""
        mutation {{
            podTerminate(input: {{ podId: "{pod_id}" }})
        }}
        """
        data = self._graphql(query)
        return {"status": "terminated", "pod_id": pod_id, "result": data}

    # ─── Connection Info ──────────────────────────────────────────────────

    def get_connection_info(self, pod_id: str) -> dict:
        """Get SSH/HTTP connection info for a pod."""
        pod = self.get_pod(pod_id)
        runtime = pod.get("runtime", {}) or {}
        ports = runtime.get("ports", []) or []

        ssh_port = None
        comfyui_port = None
        ollama_port = None

        for port in ports:
            private = port.get("privatePort")
            public = port.get("publicPort")
            ip = port.get("ip", "")
            if private == 22:
                ssh_port = public
            elif private == 8188:
                comfyui_port = public
            elif private == 11434:
                ollama_port = public

        # RunPod uses {pod_id}-{port}.proxy.runpod.net for HTTP
        proxy_base = f"https://{pod_id}-{{port}}.proxy.runpod.net"

        return {
            "pod_id": pod_id,
            "gpu_name": pod.get("machine", {}).get("gpuDisplayName", ""),
            "status": pod.get("desiredStatus", "unknown"),
            "ssh_ip": ports[0].get("ip") if ports else None,
            "ssh_port": ssh_port,
            "comfyui_port": comfyui_port,
            "comfyui_url": proxy_base.format(port=8188) if comfyui_port else None,
            "ollama_port": ollama_port,
            "ollama_url": proxy_base.format(port=11434) if ollama_port else None,
            "uptime_seconds": runtime.get("uptimeInSeconds", 0),
        }

    def wait_for_pod(self, pod_id: str, timeout: int = 300, poll_interval: int = 10) -> dict:
        """Wait for a pod to become RUNNING."""
        start = time.time()
        while time.time() - start < timeout:
            pod = self.get_pod(pod_id)
            status = pod.get("desiredStatus", "")
            runtime = pod.get("runtime")
            if status == "RUNNING" and runtime:
                return self.get_connection_info(pod_id)
            time.sleep(poll_interval)
        raise RunPodClientError(f"Pod {pod_id} did not start within {timeout}s")

    # ─── GraphQL Helper ───────────────────────────────────────────────────

    def _graphql(self, query: str) -> dict:
        """Execute a GraphQL query against RunPod API."""
        try:
            resp = httpx.post(
                RUNPOD_API_BASE,
                headers=self._headers,
                json={"query": query},
                timeout=30,
            )
            if resp.status_code != 200:
                raise RunPodClientError(f"RunPod API error ({resp.status_code}): {resp.text[:200]}")
            data = resp.json()
            if "errors" in data:
                errors = data["errors"]
                msg = errors[0].get("message", "Unknown error") if errors else "Unknown error"
                raise RunPodClientError(f"RunPod GraphQL error: {msg}")
            return data.get("data", {})
        except httpx.HTTPError as e:
            raise RunPodClientError(f"Network error: {e}")

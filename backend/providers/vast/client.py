"""Vast.ai API Client.

Handles authentication, offer discovery, instance lifecycle,
and connection info retrieval for GPU workers.

All secrets are read from environment variables — never hardcoded.
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

import httpx

VAST_API_BASE = "https://console.vast.ai/api/v0"


class VastClientError(Exception):
    """Raised when Vast.ai API returns an error."""


class VastClient:
    """Thin client around the Vast.ai REST API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("VAST_API_KEY") or os.getenv("VASTAI_API_KEY")
        if not self.api_key:
            raise VastClientError(
                "No Vast.ai API key found. Set VAST_API_KEY in .env"
            )
        self._headers = {"Authorization": f"Bearer {self.api_key}"}

    # ─── Authentication ───────────────────────────────────────────────────

    def validate_api_key(self) -> dict:
        """Validate the API key by fetching account info."""
        resp = httpx.get(
            f"{VAST_API_BASE}/users/current/",
            headers=self._headers,
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            raise VastClientError(f"Auth failed ({resp.status_code}): {resp.text}")
        return resp.json()

    # ─── Offers ───────────────────────────────────────────────────────────

    def list_offers(self) -> list[dict]:
        """List available GPU offers from the marketplace."""
        resp = httpx.get(
            f"{VAST_API_BASE}/bundles/",
            headers=self._headers,
            timeout=30,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            raise VastClientError(f"List offers failed: {resp.text}")
        data = resp.json()
        return data.get("offers", data) if isinstance(data, dict) else data

    def filter_offers(
        self,
        gpu_name: Optional[str] = None,
        min_vram_gb: float = 0,
        max_price_per_hour: Optional[float] = None,
        min_disk_gb: float = 0,
        num_gpus: int = 1,
    ) -> list[dict]:
        """Filter offers by GPU type, VRAM, price, and disk."""
        max_price = max_price_per_hour or float(
            os.getenv("VAST_MAX_PRICE_PER_HOUR", "99")
        )
        offers = self.list_offers()
        filtered = []
        for o in offers:
            if gpu_name and gpu_name.lower() not in o.get("gpu_name", "").lower():
                continue
            if o.get("gpu_ram", 0) / 1024 < min_vram_gb:
                continue
            if o.get("dph_total", 999) > max_price:
                continue
            if o.get("disk_space", 0) < min_disk_gb:
                continue
            if o.get("num_gpus", 0) < num_gpus:
                continue
            filtered.append(o)
        return filtered

    # ─── Instance Lifecycle ───────────────────────────────────────────────

    def launch_instance(
        self,
        offer_id: int,
        image: Optional[str] = None,
        disk_gb: Optional[int] = None,
        onstart: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
    ) -> dict:
        """Launch a new instance from an offer."""
        img = image or os.getenv(
            "VAST_DEFAULT_IMAGE",
            "runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04",
        )
        disk = disk_gb or int(os.getenv("VAST_DISK_GB", "80"))

        payload: dict[str, Any] = {
            "client_id": "me",
            "image": img,
            "disk": disk,
            "runtype": "ssh",
        }
        if onstart:
            payload["onstart"] = onstart
        if env:
            payload["env"] = env

        resp = httpx.put(
            f"{VAST_API_BASE}/asks/{offer_id}/",
            headers=self._headers,
            json=payload,
            timeout=30,
            follow_redirects=True,
        )
        if resp.status_code not in (200, 201):
            raise VastClientError(f"Launch failed ({resp.status_code}): {resp.text}")
        return resp.json()

    def get_instance(self, instance_id: int) -> dict:
        """Get instance details."""
        resp = httpx.get(
            f"{VAST_API_BASE}/instances/{instance_id}/",
            headers=self._headers,
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            raise VastClientError(f"Get instance failed: {resp.text}")
        return resp.json()

    def get_instances(self) -> list[dict]:
        """List all current instances."""
        resp = httpx.get(
            f"{VAST_API_BASE}/instances/",
            headers=self._headers,
            params={"owner": "me"},
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            raise VastClientError(f"List instances failed: {resp.text}")
        data = resp.json()
        return data.get("instances", data) if isinstance(data, dict) else data

    def stop_instance(self, instance_id: int) -> dict:
        """Stop (pause) an instance."""
        resp = httpx.put(
            f"{VAST_API_BASE}/instances/{instance_id}/",
            headers=self._headers,
            json={"state": "stopped"},
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            raise VastClientError(f"Stop failed: {resp.text}")
        return resp.json()

    def destroy_instance(self, instance_id: int) -> dict:
        """Permanently destroy an instance."""
        resp = httpx.delete(
            f"{VAST_API_BASE}/instances/{instance_id}/",
            headers=self._headers,
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code not in (200, 204):
            raise VastClientError(f"Destroy failed: {resp.text}")
        return {"status": "destroyed", "instance_id": instance_id}

    # ─── Connection Info ──────────────────────────────────────────────────

    def get_connection_info(self, instance_id: int) -> dict:
        """Get SSH/HTTP connection info for an instance."""
        instance = self.get_instance(instance_id)
        ports = instance.get("ports", {})
        ssh_port = None
        comfyui_port = None

        # Parse port mappings
        for port_key, port_info in ports.items():
            if "22" in port_key:
                ssh_port = port_info[0].get("HostPort") if port_info else None
            if "8188" in port_key:
                comfyui_port = port_info[0].get("HostPort") if port_info else None

        public_ip = instance.get("public_ipaddr", instance.get("ssh_host", ""))

        return {
            "instance_id": instance_id,
            "public_ip": public_ip,
            "ssh_port": ssh_port,
            "comfyui_port": comfyui_port,
            "comfyui_url": f"http://{public_ip}:{comfyui_port}" if comfyui_port else None,
            "status": instance.get("actual_status", instance.get("status_msg", "unknown")),
            "gpu_name": instance.get("gpu_name", ""),
            "gpu_ram_mb": instance.get("gpu_ram", 0),
        }

    def wait_for_instance(
        self, instance_id: int, timeout: int = 300, poll_interval: int = 10
    ) -> dict:
        """Wait for an instance to become running."""
        start = time.time()
        while time.time() - start < timeout:
            info = self.get_connection_info(instance_id)
            if info["status"] == "running":
                return info
            time.sleep(poll_interval)
        raise VastClientError(
            f"Instance {instance_id} did not start within {timeout}s"
        )

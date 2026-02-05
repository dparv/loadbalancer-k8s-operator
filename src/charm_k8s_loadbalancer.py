# Copyright 2026 dparv
# See LICENSE file for licensing details.

"""Kubernetes Service reconciliation helpers.

This module contains the non-charm-specific logic used by the charm to manage a
Kubernetes `Service` of type `LoadBalancer`.
"""

from __future__ import annotations

import ipaddress
import json
import logging
from dataclasses import dataclass
import re

logger = logging.getLogger(__name__)


class ConfigError(ValueError):
    """Raised when user configuration is invalid."""


def _validate_port(name: str, value: int) -> int:
    if not (1 <= value <= 65535):
        raise ConfigError(f"{name} must be between 1 and 65535")
    return value


def parse_selector(raw: str) -> dict[str, str]:
    """Parse a selector string into a dict.

    Supported formats:
    - comma-separated key=value pairs: "app=myapp,tier=backend"
    - JSON object: '{"app": "myapp", "tier": "backend"}'
    """
    if raw is None:
        raise ConfigError("selector must be set")

    selector = raw.strip()
    if not selector:
        raise ConfigError("selector must not be empty")

    if selector.startswith("{"):
        try:
            parsed = json.loads(selector)
        except json.JSONDecodeError as e:
            raise ConfigError(f"selector JSON is invalid: {e}") from e
        if not isinstance(parsed, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()
        ):
            raise ConfigError("selector JSON must be an object of string:string")
        if not parsed:
            raise ConfigError("selector must not be empty")
        return parsed

    result: dict[str, str] = {}
    for part in selector.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ConfigError(
                "selector must be in 'key=value' format (comma-separated) or JSON object"
            )
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise ConfigError("selector contains an empty key or value")
        result[key] = value

    if not result:
        raise ConfigError("selector must not be empty")
    return result


_DNS1123_SUBDOMAIN_PATTERN = re.compile(
    r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$"
)
_QUALIFIED_NAME_PATTERN = re.compile(r"^[A-Za-z0-9]([-A-Za-z0-9_.]*[A-Za-z0-9])?$")


def _is_valid_annotation_key(key: str) -> bool:
    if not key or len(key) > 253:
        return False

    parts = key.split("/")
    if len(parts) > 2:
        return False

    if len(parts) == 2:
        prefix, name = parts
        if not prefix or not _DNS1123_SUBDOMAIN_PATTERN.match(prefix):
            return False
    else:
        name = parts[0]

    if not name or len(name) > 63 or not _QUALIFIED_NAME_PATTERN.match(name):
        return False
    return True


def parse_annotations(raw: str) -> dict[str, str]:
    """Parse annotations string into a dict.

    Format: "key1=value1,key2=value2".
    Values may be empty ("key=").
    """
    if raw is None:
        return {}
    text = raw.strip().rstrip(",")
    if not text:
        return {}

    result: dict[str, str] = {}
    for pair in [p.strip() for p in text.split(",") if p.strip()]:
        if "=" not in pair:
            raise ConfigError(
                "loadbalancer-annotations must be in 'key=value' format (comma-separated)"
            )
        key, value = pair.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not _is_valid_annotation_key(key):
            raise ConfigError(f"invalid annotation key: {key!r}")
        result[key] = value
    return result


def parse_fixed_ip(raw: str | None) -> str | None:
    """Parse the optional fixed IP config.

    Returns a normalized IP string or None if unset.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return str(ipaddress.ip_address(text))
    except ValueError as e:
        raise ConfigError("fixed-ip must be a valid IPv4 or IPv6 address") from e


@dataclass(frozen=True)
class ServiceConfig:
    name: str
    namespace: str
    selector: dict[str, str]
    target_port: int
    lb_port: int
    annotations: dict[str, str]
    fixed_ip: str | None


def _build_service(cfg: ServiceConfig) -> Service:
    try:
        from lightkube.models.core_v1 import ServicePort, ServiceSpec
        from lightkube.models.meta_v1 import ObjectMeta
        from lightkube.resources.core_v1 import Service
    except ModuleNotFoundError as e:  # pragma: nocover
        raise ConfigError(
            "missing runtime dependency 'lightkube' (repack the charm after updating uv.lock)"
        ) from e

    return Service(
        metadata=ObjectMeta(
            name=cfg.name,
            namespace=cfg.namespace,
            labels={"app.kubernetes.io/name": cfg.name},
            annotations=cfg.annotations or None,
        ),
        spec=ServiceSpec(
            type="LoadBalancer",
            loadBalancerIP=cfg.fixed_ip or None,
            selector=cfg.selector,
            ports=[
                ServicePort(
                    port=cfg.lb_port,
                    targetPort=cfg.target_port,
                    protocol="TCP",
                    name="lb",
                )
            ],
        ),
    )


def ensure_loadbalancer_service(
    *,
    app_name: str,
    namespace: str,
    selector: dict[str, str],
    target_port: int,
    lb_port: int,
    annotations: dict[str, str] | None = None,
    fixed_ip: str | None = None,
) -> None:
    """Create or update the Service for the given config."""
    if not app_name:
        raise ConfigError("app_name must not be empty")
    if not namespace:
        raise ConfigError("namespace must not be empty")
    if not selector:
        raise ConfigError("selector must not be empty")

    target_port = _validate_port("target-port", int(target_port))
    lb_port = _validate_port("lb-port", int(lb_port))

    cfg = ServiceConfig(
        name=f"{app_name}-lb",
        namespace=namespace,
        selector=selector,
        target_port=target_port,
        lb_port=lb_port,
        annotations=annotations or {},
        fixed_ip=parse_fixed_ip(fixed_ip),
    )
    svc = _build_service(cfg)

    try:
        from lightkube import Client
        from lightkube.core.exceptions import ApiError
    except ModuleNotFoundError as e:  # pragma: nocover
        raise ConfigError(
            "missing runtime dependency 'lightkube' (repack the charm after updating uv.lock)"
        ) from e

    client = Client(namespace=namespace, field_manager=app_name)
    try:
        client.create(svc)
        logger.info("created Service %s/%s", namespace, cfg.name)
    except ApiError as e:
        if e.status.code != 409:
            raise
        client.replace(svc)
        logger.info("replaced Service %s/%s", namespace, cfg.name)


def delete_loadbalancer_service(*, app_name: str, namespace: str) -> None:
    """Delete the Service if it exists."""
    try:
        from lightkube import Client
        from lightkube.core.exceptions import ApiError
        from lightkube.resources.core_v1 import Service
    except ModuleNotFoundError as e:  # pragma: nocover
        raise ConfigError(
            "missing runtime dependency 'lightkube' (repack the charm after updating uv.lock)"
        ) from e

    name = f"{app_name}-lb"
    client = Client(namespace=namespace, field_manager=app_name)
    try:
        client.delete(Service, name=name, namespace=namespace)
    except ApiError as e:
        if e.status.code == 404:
            return
        raise

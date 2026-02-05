#!/usr/bin/env python3
# Copyright 2026 dparv
# See LICENSE file for licensing details.

"""A minimal charm that creates a Kubernetes LoadBalancer Service.

This charm intentionally does not run any workload services.
It only reconciles a `Service` object based on config options:

- `selector`: label selector for backend pods
- `target-port`: port on the selected pods
- `lb-port`: external port exposed by the LoadBalancer
- `fixed-ip`: optional IP assigned to the LoadBalancer
- `loadbalancer-annotations`: optional annotations applied to the Service
"""

import logging

import ops
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

import charm_k8s_loadbalancer

logger = logging.getLogger(__name__)


class CharmK8SLoadbalancerCharm(ops.CharmBase):
    """Create and keep in sync a Kubernetes LoadBalancer Service."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)

        self.framework.observe(self.on.install, self._on_reconcile)
        self.framework.observe(self.on.config_changed, self._on_reconcile)
        self.framework.observe(self.on.upgrade_charm, self._on_reconcile)
        self.framework.observe(self.on.remove, self._on_remove)

    def _on_reconcile(self, event: ops.EventBase) -> None:
        if not self.unit.is_leader():
            self.unit.status = WaitingStatus("waiting for leader to reconcile load balancer")
            return

        self.unit.status = MaintenanceStatus("reconciling kubernetes service")
        try:
            selector = charm_k8s_loadbalancer.parse_selector(str(self.config["selector"]))
            target_port = int(self.config["target-port"])
            lb_port = int(self.config["lb-port"])
            annotations = charm_k8s_loadbalancer.parse_annotations(
                str(self.config.get("loadbalancer-annotations", ""))
            )
            fixed_ip = self.config.get("fixed-ip", "")
            charm_k8s_loadbalancer.ensure_loadbalancer_service(
                app_name=self.app.name,
                namespace=self.model.name,
                selector=selector,
                target_port=target_port,
                lb_port=lb_port,
                annotations=annotations,
                fixed_ip=fixed_ip,
            )
        except charm_k8s_loadbalancer.ConfigError as e:
            logger.error("invalid configuration: %s", e)
            self.unit.status = BlockedStatus(str(e))
            return
        except Exception as e:  # pragma: nocover
            logger.exception("failed to reconcile service")
            self.unit.status = BlockedStatus(f"failed to reconcile service: {e}")
            return

        self.unit.status = ActiveStatus("load balancer service ready")

    def _on_remove(self, event: ops.RemoveEvent) -> None:
        if not self.unit.is_leader():
            return
        try:
            charm_k8s_loadbalancer.delete_loadbalancer_service(
                app_name=self.app.name,
                namespace=self.model.name,
            )
        except Exception:  # pragma: nocover
            logger.exception("failed to delete service")


if __name__ == "__main__":  # pragma: nocover
    ops.main(CharmK8SLoadbalancerCharm)

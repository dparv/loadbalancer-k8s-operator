"""Unit tests for the service-only load balancer charm."""

import pytest
from ops import testing

from charm import CharmK8SLoadbalancerCharm


def test_non_leader_waits_for_reconcile(monkeypatch: pytest.MonkeyPatch):
    called = {"count": 0}

    def _ensure(*args, **kwargs):
        called["count"] += 1

    monkeypatch.setattr("charm.charm_k8s_loadbalancer.ensure_loadbalancer_service", _ensure)

    ctx = testing.Context(CharmK8SLoadbalancerCharm)
    state_in = testing.State(leader=False)

    state_out = ctx.run(ctx.on.config_changed(), state_in)

    assert called["count"] == 0
    assert isinstance(state_out.unit_status, testing.WaitingStatus)


def test_leader_reconciles_service(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def _ensure(*, app_name, namespace, selector, target_port, lb_port, annotations=None, fixed_ip=None):
        captured.update(
            {
                "app_name": app_name,
                "namespace": namespace,
                "selector": selector,
                "target_port": target_port,
                "lb_port": lb_port,
                "annotations": annotations,
                "fixed_ip": fixed_ip,
            }
        )

    monkeypatch.setattr("charm.charm_k8s_loadbalancer.ensure_loadbalancer_service", _ensure)

    ctx = testing.Context(CharmK8SLoadbalancerCharm)
    state_in = testing.State(
        leader=True,
        config={
            "selector": "app.kubernetes.io/name=myapp",
            "target-port": 8080,
            "lb-port": 80,
            "loadbalancer-annotations": "service.beta.kubernetes.io/aws-load-balancer-type=nlb",
        },
    )

    state_out = ctx.run(ctx.on.config_changed(), state_in)

    assert captured["selector"] == {"app.kubernetes.io/name": "myapp"}
    assert captured["target_port"] == 8080
    assert captured["lb_port"] == 80
    assert captured["annotations"] == {
        "service.beta.kubernetes.io/aws-load-balancer-type": "nlb",
    }
    assert captured["fixed_ip"] == ""
    assert isinstance(state_out.unit_status, testing.ActiveStatus)


def test_invalid_fixed_ip_blocks(monkeypatch: pytest.MonkeyPatch):
    from charm import charm_k8s_loadbalancer

    def _ensure(*, fixed_ip=None, **kwargs):
        # Emulate validation that happens in ensure_loadbalancer_service without
        # requiring Lightkube.
        charm_k8s_loadbalancer.parse_fixed_ip(fixed_ip)

    monkeypatch.setattr("charm.charm_k8s_loadbalancer.ensure_loadbalancer_service", _ensure)

    ctx = testing.Context(CharmK8SLoadbalancerCharm)
    state_in = testing.State(
        leader=True,
        config={
            "selector": "app=myapp",
            "target-port": 80,
            "lb-port": 80,
            "fixed-ip": "not-an-ip",
        },
    )

    state_out = ctx.run(ctx.on.config_changed(), state_in)
    assert isinstance(state_out.unit_status, testing.BlockedStatus)


def test_invalid_selector_blocks(monkeypatch: pytest.MonkeyPatch):
    def _ensure(*args, **kwargs):
        raise AssertionError("ensure_loadbalancer_service should not be called")

    monkeypatch.setattr("charm.charm_k8s_loadbalancer.ensure_loadbalancer_service", _ensure)

    ctx = testing.Context(CharmK8SLoadbalancerCharm)
    state_in = testing.State(
        leader=True,
        config={
            "selector": "not-a-kv",
            "target-port": 80,
            "lb-port": 80,
        },
    )

    state_out = ctx.run(ctx.on.config_changed(), state_in)
    assert isinstance(state_out.unit_status, testing.BlockedStatus)


def test_invalid_annotation_key_blocks(monkeypatch: pytest.MonkeyPatch):
    def _ensure(*args, **kwargs):
        raise AssertionError("ensure_loadbalancer_service should not be called")

    monkeypatch.setattr("charm.charm_k8s_loadbalancer.ensure_loadbalancer_service", _ensure)

    ctx = testing.Context(CharmK8SLoadbalancerCharm)
    state_in = testing.State(
        leader=True,
        config={
            "selector": "app=myapp",
            "target-port": 80,
            "lb-port": 80,
            "loadbalancer-annotations": "not a key=value",
        },
    )

    state_out = ctx.run(ctx.on.config_changed(), state_in)
    assert isinstance(state_out.unit_status, testing.BlockedStatus)

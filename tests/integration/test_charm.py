# Copyright 2026 dparv
# See LICENSE file for licensing details.
#
# The integration tests use the Jubilant library. See https://documentation.ubuntu.com/jubilant/
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import logging
import pathlib

import jubilant
import yaml

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(pathlib.Path("charmcraft.yaml").read_text())


def test_deploy(charm: pathlib.Path, juju: jubilant.Juju):
    """Deploy the charm under test."""
    resources = {"image": METADATA["resources"]["image"]["upstream-source"]}
    juju.deploy(charm.resolve(), app="charm-k8s-loadbalancer", resources=resources)
    juju.wait(jubilant.all_active)


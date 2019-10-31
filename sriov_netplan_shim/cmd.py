#!/usr/bin/env python3
#
# Copyright 2019 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import logging
import os
import yaml

from sriov_netplan_shim import pci


DEFAULT_CONF_FILE = "/etc/sriov-netplan-shim/interfaces.yaml"


def configure():
    """Configure SR-IOV VF's with configuration from interfaces.yaml"""
    configuration = {}
    if os.path.exists(DEFAULT_CONF_FILE):
        with open(DEFAULT_CONF_FILE, "r") as conf:
            configuration = yaml.load(conf)
    else:
        logging.warn("No configuration file found, skipping configuration")
        return

    interfaces = configuration["interfaces"]
    for interface_name in interfaces:
        num_vfs = interfaces[interface_name]["num_vfs"]
        devices = pci.PCINetDevices()
        device = devices.get_device_from_interface_name(interface_name)
        if device and device.sriov:
            if num_vfs > device.sriov_totalvfs:
                logging.warn(
                    "Requested value for sriov_numfs ({}) too "
                    "high for interface {}. Falling back to "
                    "interface totalvfs "
                    "value: {}".format(
                        num_vfs, device.interface_name, device.sriov_totalvfs
                    )
                )
                num_vfs = device.sriov_totalvfs

            logging.info(
                "Configuring SR-IOV device {} with {} "
                "VF's".format(device.interface_name, num_vfs)
            )
            device.set_sriov_numvfs(num_vfs)


def main():
    """Main entry point for sriov-netplan-shim"""
    parser = argparse.ArgumentParser("sriov-netplan-shim")
    parser.set_defaults(prog=parser.prog)
    subparsers = parser.add_subparsers(
        title="subcommands",
        description="valid subcommands",
        help="sub-command help",
    )
    show_subparser = subparsers.add_parser(
        "configure", help="Configure SR-IOV adapters with VF functions"
    )
    show_subparser.set_defaults(func=configure)

    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)

    try:
        args.func()
    except Exception as e:
        raise SystemExit("{prog}: {msg}".format(prog=args.prog, msg=e))

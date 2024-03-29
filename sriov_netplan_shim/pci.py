#!/usr/bin/env python3
#
# Copyright 2016 Canonical Ltd
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

import glob
import itertools
import logging
import os
import re
import shlex
import subprocess
import typing


def format_pci_addr(pci_addr: str) -> str:
    """Format a PCI address with 0 fill for parts

    :param: pci_addr: unformatted PCI address
    :type: str
    :returns: formatted PCI address
    :rtype: str
    """
    domain, bus, slot_func = pci_addr.split(":")
    slot, func = slot_func.split(".")
    return "{}:{}:{}.{}".format(
        domain.zfill(4), bus.zfill(2), slot.zfill(2), func
    )


def get_sysnet_interfaces_and_macs() -> list:
    """Catalog interface information from local system

    each device dict contains:

        interface: logical name
        mac_address: MAC address
        pci_address: PCI address
        state: Current interface state (up/down)
        sriov: Boolean indicating whether interface is an SR-IOV
               capable device.
        sriov_totalvfs: Total VF capacity of device
        sriov_numvfs: Configured VF capacity of device

    :returns: array of dict objects containing details of each interface
    :rtype: list
    """
    net_devs = []
    for sdir in itertools.chain(
            glob.glob("/sys/bus/pci/devices/*/net/../"),
            glob.glob("/sys/bus/pci/devices/*/virtio*/net/../")):
        fq_path = os.path.realpath(sdir)
        path = fq_path.split("/")
        if "virtio" in path[-1]:
            pci_address = path[-2]
        else:
            pci_address = path[-1]
        ifname = get_sysnet_interface(sdir)
        if not ifname:
            logging.warn("Unable to determine interface name for PCI "
                         "device {}".format(pci_address))
            continue
        device = {
            "interface": ifname,
            "mac_address": get_sysnet_mac(sdir, ifname),
            "pci_address": pci_address,
            "state": get_sysnet_device_state(sdir, ifname),
            "sriov": is_sriov(sdir),
        }
        if device["sriov"]:
            device["sriov_totalvfs"] = get_sriov_totalvfs(sdir)
            device["sriov_numvfs"] = get_sriov_numvfs(sdir)
        net_devs.append(device)

    return net_devs


def get_sysnet_mac(sysdir: str, ifname: str) -> str:
    """Determine MAC address for a device

    :param: sysdir: path to device /sys directory
    :type: str
    :returns: MAC address of device
    :rtype: str
    """
    mac_addr_file = os.path.join(sysdir, "net", ifname, "address")
    with open(mac_addr_file, "r") as f:
        read_data = f.read()
    return read_data.strip()


def get_sysnet_device_state(sysdir: str, ifname: str) -> str:
    """Read operational state of a device

    :param: sysdir: path to device /sys directory
    :type: str
    :returns: current device state
    :rtype: str
    """
    state_file = os.path.join(sysdir, "net", ifname, "operstate")
    with open(state_file, "r") as f:
        read_data = f.read()
    return read_data.strip()


def is_sriov(sysdir: str) -> bool:
    """Determine whether a device is SR-IOV capable

    :param: sysdir: path to device /sys directory
    :type: str
    :returns: whether device is SR-IOV capable or not
    :rtype: bool
    """
    return os.path.exists(os.path.join(sysdir, "sriov_totalvfs"))


def get_sriov_totalvfs(sysdir: str) -> int:
    """Read total VF capacity for a device

    :param: sysdir: path to device /sys directory
    :type: str
    :returns: number of VF's the device supports
    :rtype: int
    """
    sriov_totalvfs_file = os.path.join(sysdir, "sriov_totalvfs")
    with open(sriov_totalvfs_file, "r") as f:
        read_data = f.read()
    return int(read_data.strip())


def get_sriov_numvfs(sysdir: str) -> int:
    """Read configured VF capacity for a device

    :param: sysdir: path to device /sys directory
    :type: str
    :returns: number of VF's the device is configured with
    :rtype: int
    """
    sriov_numvfs_file = os.path.join(sysdir, "sriov_numvfs")
    with open(sriov_numvfs_file, "r") as f:
        read_data = f.read()
    return int(read_data.strip())


# https://github.com/libvirt/libvirt/commit/5b1c525b1f3608156884aed0dc5e925306c1e260
PF_PHYS_PORT_NAME_REGEX = re.compile(r"(p[0-9]+$)|(p[0-9]+s[0-9]+$)",
                                     re.IGNORECASE)


def _phys_port_name_is_pf(sysnetdir: str) -> typing.Optional[bool]:
    try:
        with open(os.path.join(sysnetdir, "phys_port_name"), "r") as fin:
            return (PF_PHYS_PORT_NAME_REGEX.match(fin.read().strip())
                    is not None)
    except OSError:
        return


def get_sysnet_interface(sysdir: str) -> typing.Optional[str]:
    sysnetdir = os.path.join(sysdir, "net")
    netdevs = os.listdir(sysnetdir)
    # Return early in case the PCI device only has one netdev
    if len(netdevs) == 1:
        return netdevs[0]

    # When a PCI device has multiple netdevs we need to figure out which one
    # represents the PF
    for netdev in netdevs:
        if _phys_port_name_is_pf(os.path.join(sysnetdir, netdev)):
            return netdev


def get_pci_ethernet_addresses() -> list:
    """Generate list of PCI addresses for all network adapters

    :returns: list of PCI addresses
    :rtype: list
    """
    cmd = ["lspci", "-m", "-D"]
    lspci_output = subprocess.check_output(cmd).decode("UTF-8")
    pci_addresses = []
    for line in lspci_output.split("\n"):
        columns = shlex.split(line)
        if len(columns) > 1 and columns[1] == "Ethernet controller":
            pci_address = columns[0]
            pci_addresses.append(format_pci_addr(pci_address))
    return pci_addresses


class PCINetDevice(object):
    def __init__(self, pci_address):
        self.pci_address = pci_address
        self.interface_name = None
        self.mac_address = None
        self.state = None
        self.sriov = False
        self.sriov_totalvfs = None
        self.sriov_numvfs = None
        self.update_attributes()

    def update_attributes(self):
        self.update_interface_info()

    def update_interface_info(self):
        net_devices = get_sysnet_interfaces_and_macs()
        for interface in net_devices:
            if self.pci_address == interface["pci_address"]:
                self.interface_name = interface["interface"]
                self.mac_address = interface["mac_address"]
                self.state = interface["state"]
                self.sriov = interface["sriov"]
                if self.sriov:
                    self.sriov_totalvfs = interface["sriov_totalvfs"]
                    self.sriov_numvfs = interface["sriov_numvfs"]

    def _set_sriov_numvfs(self, numvfs: int):
        sdevice = os.path.join(
            "/sys/bus/pci/devices", self.pci_address, "sriov_numvfs"
        )
        with open(sdevice, "w") as sh:
            sh.write(str(numvfs))
        self.update_attributes()

    def set_sriov_numvfs(self, numvfs: int) -> bool:
        """Set the number of VF devices for a SR-IOV PF

        Assuming the device is an SR-IOV device, this function will attempt
        to change the number of VF's created by the PF.

        @param numvfs: integer to set the current number of VF's to
        @returns boolean indicating whether any changes where made
        """
        if self.sriov and numvfs != self.sriov_numvfs:
            # NOTE(fnordahl): run-time change of numvfs is disallowed
            # without resetting to 0 first.
            self._set_sriov_numvfs(0)
            self._set_sriov_numvfs(numvfs)
            return True
        return False


class PCINetDevices(object):
    def __init__(self):
        self.pci_devices = [
            PCINetDevice(dev) for dev in get_pci_ethernet_addresses()
        ]

    def update_devices(self):
        for pcidev in self.pci_devices:
            pcidev.update_attributes()

    def get_macs(self) -> list:
        macs = []
        for pcidev in self.pci_devices:
            if pcidev.mac_address:
                macs.append(pcidev.mac_address)
        return macs

    def get_device_from_mac(self, mac: str) -> PCINetDevice:
        for pcidev in self.pci_devices:
            if pcidev.mac_address == mac:
                return pcidev
        return None

    def get_device_from_pci_address(self, pci_addr: str) -> PCINetDevice:
        for pcidev in self.pci_devices:
            if pcidev.pci_address == pci_addr:
                return pcidev
        return None

    def get_device_from_interface_name(
        self, interface_name: str
    ) -> PCINetDevice:
        for pcidev in self.pci_devices:
            if pcidev.interface_name == interface_name:
                return pcidev
        return None

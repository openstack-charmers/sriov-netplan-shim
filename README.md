[![Build Status](https://travis-ci.org/openstack-charmers/sriov-netplan-shim.svg?branch=master)](https://travis-ci.org/openstack-charmers/sriov-netplan-shim)

# SR-IOV VF device configuration

A simple utility that configures SR-IOV VF devices on network adapters
on boot.

Configuration is read from ``/etc/sriov-netplan-shim/interfaces.yaml``
using the following format:

```yaml
interfaces:
    enp3s0f0:
        num_vfs: 64
    enp3s0f1:
        num_vfs: 64
```

Interfaces will be configured with the supplied number or the maximum
number of VF's that the device can support (if num\_vfs exceeds the
device maximum value).

Devices not found on the installed system will be skipped.

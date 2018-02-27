#!/usr/bin/env python3

import maas.client
import os
import sys

BLOCK_SIZE = 4*1024**2

client = maas.client.connect(
    "http://maas-dc1r01n01.admin.eu-csr.hub.k.grp:5240/MAAS",
    apikey=os.getenv("MAAS_API_KEY")
)

for machine in client.machines.list():
    if machine.hostname == sys.argv[1]:
        break
else:
    raise

if machine.status != maas.client.enum.NodeStatus.READY:
    raise RuntimeError("machine %s should be READY" % machine.hostname)

for interface in machine.interfaces:
    if interface.type == maas.client.enum.InterfaceType.BOND:
        interface.delete()

for vg in machine.volume_groups:
    vg.delete()

for disk in machine.block_devices:
    if disk.type == maas.client.enum.BlockDeviceType.VIRTUAL:
        disk.delete()

for disk in machine.block_devices:
    if disk.type == maas.client.enum.BlockDeviceType.PHYSICAL:
        for partition in disk.partitions:
            partition.delete()

machine.refresh()

fabric = client.fabrics.get_default()
VLANS = dict((vlan.name, vlan) for vlan in fabric.vlans)

parents = []
for interface in machine.interfaces:
    interface.disconnect()
    if not interface.name.startswith(machine.boot_interface.name[:-1]):
        parents.append(interface)

if len(parents) != 2:
    raise

for interface in parents:
    interface.vlan = fabric.vlans.get_default()
    interface.save()

bond = machine.interfaces.create(
    name="bond0",
    interface_type=maas.client.enum.InterfaceType.BOND,
    parents=parents,
    bond_mode="802.3ad",
    bond_lacp_rate="fast",
    bond_xmit_hash_policy="layer2+3"
)

vlans = {"mgmt": 1792, "vxlan": 1793, "storage": 1794}

if machine.hostname.startswith("controller"):
    del vlans["storage"]

if machine.hostname.startswith("storage"):
    del vlans["vxlan"]

for vlan, vid in vlans.items():
    vif = machine.interfaces.create(
        name="bond0.%d" % vid,
        interface_type=maas.client.enum.InterfaceType.VLAN,
        parent=bond,
        vlan=VLANS[vlan]
    )

    machine.interfaces.create(
        name="br-%s" % vlan,
        interface_type=maas.client.enum.InterfaceType.BRIDGE,
        parent=vif
    )

if not machine.hostname.startswith("storage"):
    machine.interfaces.create(
        name="br-vlan",
        interface_type=maas.client.enum.InterfaceType.BRIDGE,
        parent=bond
    )


def subnet(vlan):
    for subnet in client.subnets.list():
        if subnet.name == "rack2" and subnet.vlan.id == VLANS[vlan].id:
            return subnet


def address(subnet, host):
    split = subnet.cidr.split(".")
    split[-1] = str(host)
    return ".".join(split)


machine.boot_interface.links.create(
        mode=maas.client.enum.LinkMode.DHCP,
        subnet=subnet("untagged")
)

machine.interfaces.get_by_name("br-mgmt").links.create(
        mode=maas.client.enum.LinkMode.STATIC,
        subnet=subnet("mgmt"),
        ip_address=address(subnet("mgmt"), sys.argv[2]),
        default_gateway=True
)

if machine.hostname.startswith("compute"):
    machine.interfaces.get_by_name("br-vxlan").links.create(
        mode=maas.client.enum.LinkMode.STATIC,
        subnet=subnet("vxlan"),
        ip_address=address(subnet("vxlan"), sys.argv[2]),
    )
    machine.interfaces.get_by_name("br-storage").links.create(
        mode=maas.client.enum.LinkMode.STATIC,
        subnet=subnet("storage"),
        ip_address=address(subnet("storage"), sys.argv[2]),
    )

disks = []
for disk in machine.block_devices:
    if "ssd" in disk.tags and "sata" in disk.tags and \
            disk.model == machine.boot_disk.model and \
            disk.size == machine.boot_disk.size:
        disks.append(disk)

if len(disks) != 2:
    raise

partitions = []
for disk in disks:
        # Align partition on 4 MiB blocks
        blocks = disk.available_size // BLOCK_SIZE
        size = blocks * BLOCK_SIZE - 1

        partitions.append(disk.partitions.create(size=size))

raid = machine.raids.create(
    name="md0",
    level=maas.client.enum.RaidLevel.RAID_1,
    devices=partitions,
    spare_devices=[],
)

raid.virtual_device.format("ext4")
raid.virtual_device.mount("/")

if machine.hostname.startswith("controller"):
    machine.refresh()
    devices = [device for device in machine.block_devices
               if device.used_for == "Unused"]
    if devices:
        machine.volume_groups.create(
            name="lxc",
            devices=devices
        )

user_data = b'''#cloud-config
users:
  - default
  - name: root
    ssh-authorized-keys:
      - ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC9IO1q9mFYROZ13WEdkI2O1o7HzxtsKD/bu7SeMm7KLGQd4wmR4PjhUw9wyLg4Bw/7C7bObX9IxiY/0m3mZ3YTUq1Z9E9OllPaIoU95U17n+Xz9XujwyfJNOxKsHBUr5MMuu/fseQVgSQD84LUWfKl29tb9ppLzoaYHO/hRx9niXcKXoEv84toBte1g87RHPWoHxkoh2I4wy4SQVh5Eg/ur+fCw5qo3mvAIPJv62xV5wN/ACCcCw3Yl2iRf7ez12Jjfi13nGQCM8Fc71FrttBLHB3vXnDEkF6A96SGG/IQHBDFytNM4ohw9/WMNGV1AHJ098LhSIEYyTCRGAA30edsDnwAXJPi4AH2HgsbluhZQDM1+4uS3EqoOulre3Mjj7lAHAduaWuSplzUzct5JBmWwi6e8tLd3hcaEt93/QKJawaLTIg6iMgdBJYGAFTbhw/TjlVN637wqt6/FWKSI64qg/pSaawTO/9vuwdnk6h1n2moz9HtI8H20vFBtpk0eUtjJhJP2GqMvgR+G5OLAsS4xzZrQsfr6wQOWQ2QUbWGbAh6pWoLullVC+2JFm9dOeqnYzh/7ELN3sEJBDj6SuytEiRo0JFzx1hZ8P2DsoNpTRVy0XNa2MGkSy/Ka6I7lUOkYYjpXI39Bb9K0MhiCMMB9fKJHw0H32M56JRXbdjX2w== ubuntu@maas
packages:
  - debootstrap
  - python
'''

machine.deploy(user_data=user_data)

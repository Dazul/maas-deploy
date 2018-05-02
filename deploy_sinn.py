#!/usr/bin/env python3

import maas.client
import os
import sys
import yaml

BLOCK_SIZE = 4*1024**2

def cleanup_machine(machine):
    if machine.status != maas.client.enum.NodeStatus.READY:
        print("machine %s is not READY" % machine.hostname)
        sys.exit(1)

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

def configure_system_disks(machine):
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

    machine.refresh()

def get_subnet(client, subnet_name):
    for subnet in client.subnets.list():
        if subnet.name == subnet_name:
            return subnet

def configure_boot_interface(machine, client):
    machine.boot_interface.links[0].delete()
    machine.boot_interface.links.create(mode=maas.client.enum.LinkMode.DHCP)

#    parents = []
#    for interface in machine.interfaces:
#        if interface.name.startswith("enp4"):
#            parents.append(interface)
#    
#    bond = machine.interfaces.create(
#        name="bond0",
#        interface_type=maas.client.enum.InterfaceType.BOND,
#        parents=parents,
#        bond_mode="802.3ad",
#        bond_lacp_rate="fast",
#        bond_xmit_hash_policy="layer3+4"
#    )
#    
#    bond.links.create(
#        mode=maas.client.enum.LinkMode.STATIC,
#        subnet=get_subnet(client, "Sinn"),
#        ip_address="185.35.62.12",
#        default_gateway=True
#    )

    machine.refresh()

def main():

    params = yaml.load(open(sys.argv[1]))

    client = maas.client.connect(
        "http://maas.admin.eu-zrh.hub.k.grp:5240/MAAS",
        apikey=os.getenv("MAAS_API_KEY")
    )
    
    for machine in client.machines.list():
        if machine.hostname == list(params.keys())[0]:
            break
    else:
        raise

    cleanup_machine(machine)
    configure_boot_interface(machine, client)
    configure_system_disks(machine)
#    machine.deploy()

if __name__ == "__main__":
    main()

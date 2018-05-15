#!/usr/bin/env python3

import maas.client
import os
import sys
import yaml

BLOCK_SIZE = 4*1024**2

def cleanup_machine(machine):
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

def configure_network(machine, client, net_bounding=None):
    machine.boot_interface.links[0].delete()
    machine.boot_interface.links.create(mode=maas.client.enum.LinkMode.DHCP)

    if net_bounding is not None:
        parents = []
        for interface in machine.interfaces:
            import pdb; pdb.set_trace()
            if interface.name in net_bounding['slaves']:
                parents.append(interface)
        
        bond = machine.interfaces.create(
            name=net_bounding['name'],
            interface_type=maas.client.enum.InterfaceType.BOND,
            parents=parents,
            bond_mode="802.3ad",
            bond_lacp_rate="fast",
            bond_xmit_hash_policy="layer3+4"
        )

    machine.refresh()

def main():
    
    hostname = sys.argv[1]
    config = yaml.load(open(sys.argv[2]))
    root = list(config.keys())[0]

    net_bounding = None
    if 'net_bounding' in config[root]:
        net_bounding = config[root]['net_bounding']

    client = maas.client.connect(
        "http://maas.admin.eu-zrh.hub.k.grp:5240/MAAS",
        apikey=os.getenv("MAAS_API_KEY")
    )
    
    for machine in client.machines.list():
        if machine.hostname == hostname:
            break
    else:
        raise

    if machine.status != maas.client.enum.NodeStatus.READY:
        print("machine %s is not READY" % machine.hostname)
        sys.exit(1)

    cleanup_machine(machine)
    configure_network(machine, client, net_bounding)
#    configure_system_disks(machine)
#    machine.deploy()

if __name__ == "__main__":
    main()

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

def define_os_disks(machine, os_raid=None, os_partitions=None):
    os_disks = []

    # default disk discovery
    if os_raid is None:
        by_size = {}
        for disk in machine.block_devices:
            if disk.size in by_size.keys():
                by_size[disk.size].append(disk)
            else:
                by_size[disk.size] = [disk]

        found_os_disks = False
        for key in by_size:
            if len(by_size[key]) == 2:
                if not found_os_disks:
                    found_os_disks = True
                    os_disks = by_size[key]
                elif found_os_disks:
                    print("Ambiguous pair of disks")
                    sys.exit(-1)

        if not found_os_disks:
            print("Os disks can not be automatically discover")
            sys.exit(-1)

        return os_disks

    # disks defined
    if 'disks' in os_raid.keys() and len(os_raid['disks']) == 2:
        for disk in machine.block_devices:
            if disk.name in os_raid['disks']:
                os_disks.append(disk)
        if len(os_disks) != 2:
            print("Disks not properly defined")
            sys.exit(-1)

        return os_disks

def configure_system_disks(machine, os_raid=None, os_partitions=None):
    disks = define_os_disks(machine, os_raid)

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

    if os_partitions is None:
        raid.virtual_device.format("ext4")
        raid.virtual_device.mount("/")
    else:
        for os_part, infos in os_partitions.items():
            part = raid.virtual_device.partitions.create(infos["size"])
            part.format(infos["filesystem"])
            part.mount(os_part)

    machine.refresh()

def get_subnet(client, subnet_name):
    for subnet in client.subnets.list():
        if subnet.name == subnet_name:
            return subnet

def configure_network(machine, client, net_bonding=None):
    machine.boot_interface.links[0].delete()
    machine.boot_interface.links.create(mode=maas.client.enum.LinkMode.DHCP)

    if net_bonding is not None:
        parents = []
        for interface in machine.interfaces:
            if interface.name in net_bonding['slaves']:
                parents.append(interface)

        bond = machine.interfaces.create(
            name=net_bonding['name'],
            interface_type=maas.client.enum.InterfaceType.BOND,
            parents=parents,
            bond_mode="802.3ad",
            bond_lacp_rate="fast",
            bond_xmit_hash_policy="layer3+4"
        )

        if 'vlans' in net_bonding:
            fabric = client.fabrics.get_default()
            VLANS = dict((vlan.name, vlan) for vlan in fabric.vlans)
            bond.vlan = fabric.vlans.get_default()
            bond.save()

            fabric = client.fabrics.get_default()
            VLANS = dict((vlan.name, vlan) for vlan in fabric.vlans)
            for vlan, vid in net_bonding['vlans'].items():
                vif = machine.interfaces.create(
                    name="bond0.%d" % vid,
                    interface_type=maas.client.enum.InterfaceType.VLAN,
                    parent=bond,
                    vlan=VLANS[str(vid)]
                )

                machine.interfaces.create(
                    name="br-%s" % vlan,
                    interface_type=maas.client.enum.InterfaceType.BRIDGE,
                    parent=vif
                )

    machine.refresh()


def get_item_configs(key, host_config, template):
    item = None
    if key in host_config:
        item = host_config[key]
    elif key in template:
        item = template[key]
    return item

def build_user_data(host_config, template):
    user_data = {}

    if 'packages' in host_config:
        user_data['packages'] = host_config['packages']
    elif 'packages' in template:
        user_data['packages'] = template['packages']

    if 'sources' in host_config:
        user_data['apt'] = {'preserve_sources_list': True,
                            'sources': host_config['sources']}
    elif 'sources' in template:
        user_data['apt'] = {'preserve_sources_list': True,
                            'sources': template['sources']}

    user_data = b"#cloud-config\n" + yaml.dump(user_data).encode("utf-8")
    return user_data

def parse_config(host_config):
    if host_config is None:
        host_config = {}

    if 'template' in host_config:
        template = yaml.load(open(host_config['template']))
    else:
        template = {}

    net_bonding = get_item_configs('net_bonding', host_config, template)
    os_raid = get_item_configs('os_raid1', host_config, template)
    os_partitions = get_item_configs('os_partitions', host_config, template)
    distro_name = get_item_configs('os', host_config, template)
    user_data = build_user_data(host_config, template)
    return net_bonding, os_raid, os_partitions, distro_name, user_data

def main():

    yaml_config = yaml.load(open(sys.argv[1]))
    hostname = list(yaml_config.keys())[0]

    client = maas.client.connect(
        os.getenv("MAAS_API_URL"),
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

    config_items = parse_config(yaml_config[hostname])
    net_bonding = config_items[0]
    os_raid = config_items[1]
    os_partitions = config_items[2]
    distro_name = config_items[3]
    user_data = config_items[4]

    cleanup_machine(machine)
    configure_network(machine, client, net_bonding)
    configure_system_disks(machine, os_raid, os_partitions)


    machine.deploy(distro_series=distro_name, user_data=user_data)
    print("Machine %s is now in %s state." % (hostname, machine.status._name_ ))

if __name__ == "__main__":
    main()

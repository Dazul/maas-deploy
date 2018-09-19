#!/usr/bin/env python3

import maas.client
import os
import sys
import argparse
import yaml

BLOCK_SIZE = 4*1024**2

def cleanup_machine(machine):
    for interface in machine.interfaces:
        if interface.type == maas.client.enum.InterfaceType.BOND:
            interface.delete()
        elif interface.type == maas.client.enum.InterfaceType.PHYSICAL:
            interface.disconnect()

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
    disks[0].set_as_boot_disk()
    partitions = []
    for disk in disks:
        # Align partition on 4 MiB blocks
        blocks = disk.available_size // BLOCK_SIZE
        size = blocks * BLOCK_SIZE - 1
        try:
            partitions.append(disk.partitions.create(size=size))
        except:
            partitions.append(disk.partitions.create(size=size-512000000))

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

def get_fabric(client, fabric_name):
    for fabric in client.fabrics.list():
        if fabric.name == fabric_name:
            return fabric

def get_subnet(client, subnet_name):
    for subnet in client.subnets.list():
        if subnet.name == subnet_name:
            return subnet

def configure_vlans(machine, client, vname, vdata, bond, VLANS, default_gateway):
    if 'subnet' in vdata:
        vif = machine.interfaces.create(
            name="bond0.%s" % vdata['vlan'],
            interface_type=maas.client.enum.InterfaceType.VLAN,
            parent=bond,
            vlan=VLANS[str(vdata['vlan'])]
        )

        iface = machine.interfaces.create(
            name="br-%s" % vname,
            interface_type=maas.client.enum.InterfaceType.BRIDGE,
            parent=vif
        )

        if 'ip' in vdata:
            iface.links.create(
                mode=maas.client.enum.LinkMode.STATIC,
                subnet=get_subnet(client, vdata['subnet']),
                ip_address=vdata['ip'],
                default_gateway=default_gateway
            )
    else:
        iface = machine.interfaces.create(
            name="br-%s" % vname,
            interface_type=maas.client.enum.InterfaceType.BRIDGE,
            parent=bond,
        )

def configure_network(machine, client, net_bonding=None, admin_net='None'):
    if admin_net is None:
        admin_net = "None"

    if len(machine.boot_interface.links) > 0:
        machine.boot_interface.links[0].delete()

    if admin_net != 'None':
        def_sub = get_subnet(client, admin_net)
        machine.boot_interface.links.create(mode=maas.client.enum.LinkMode.DHCP, subnet=def_sub)

    if net_bonding is not None:
        parents = []
        for interface in machine.interfaces:
            if interface.name in net_bonding['slaves']:
                parents.append(interface)

        for parent in parents:
            parent.disconnect()

        bond = machine.interfaces.create(
            name=net_bonding['name'],
            interface_type=maas.client.enum.InterfaceType.BOND,
            parents=parents,
            bond_mode="802.3ad",
            bond_lacp_rate="fast",
            bond_xmit_hash_policy="layer3+4"
        )

        if 'vlans' in net_bonding:
            fabric = get_fabric(client, net_bonding['fabric'])
            VLANS = dict((vlan.name, vlan) for vlan in fabric.vlans)
            bond.vlan = fabric.vlans.get_default()
            bond.save()

            VLANS = dict((vlan.name, vlan) for vlan in fabric.vlans)
            for vname, vdata in net_bonding['vlans'].items():
                if 'default_gateway' in vdata:
                    configure_vlans(machine, client, vname, vdata, bond, VLANS, True)
                    break
            for vname, vdata in net_bonding['vlans'].items():
                if 'default_gateway' not in vdata:
                    configure_vlans(machine, client, vname, vdata, bond, VLANS, False)

    machine.refresh()


def configure_jbod_disks(machine, jbod_conf):
    for disk_conf in jbod_conf:
        for disk in machine.block_devices:
            if disk.name == disk_conf['device']:
                break
        part = disk.partitions.create(disk.available_size - 512000000)
        part.format(disk_conf['fs'])
        part.mount(disk_conf['mountpoint'])
        machine.refresh()

def set_unused_disks(machine, user_data, unused_disks):
    if 'jbod_disks' in unused_disks:
        configure_jbod_disks(machine, unused_disks['jbod_disks'])
    else:
        unused = ["/dev/" + device.name for device in machine.block_devices
                  if device.used_for == "Unused"]
        bootcmd = unused_disks['disk_array']
        bootcmd.extend(unused)
        user_data.update({"bootcmd": [bootcmd]})
        if 'step2' in unused_disks:
            step2 = unused_disks['step2']
            user_data['bootcmd'].append(step2)

def build_user_data(machine, host_config, template):
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

    if 'unused_disks' in host_config:
        set_unused_disks(machine, user_data, host_config['unused_disks'])
    elif 'unused_disks' in template:
        set_unused_disks(machine, user_data, template['unused_disks'])

    user_data = b"#cloud-config\n" + yaml.dump(user_data).encode("utf-8")
    return user_data

def get_item_configs(key, host_config, template):
    item = None
    if key in host_config:
        item = host_config[key]
    elif key in template:
        item = template[key]
    return item

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
    kernel_version = get_item_configs('kernel', host_config, template)
    admin_net = get_item_configs('admin_net', host_config, template)
    return net_bonding, os_raid, os_partitions, distro_name, host_config, template, kernel_version, admin_net

def run_machine(hostname, yaml_config, client):
    for machine in client.machines.list():
        if machine.hostname == hostname:
            break
    else:
        print("No machine named %s found" % hostname)
        return

    if machine.status != maas.client.enum.NodeStatus.READY:
        print("machine %s is not READY" % machine.hostname)
        return
    print("Starting deployement of %s" % machine.hostname)
    config_items = parse_config(yaml_config)
    net_bonding = config_items[0]
    os_raid = config_items[1]
    os_partitions = config_items[2]
    distro_name = config_items[3]
    host_config = config_items[4]
    template = config_items[5]
    kernel_version = config_items[6]
    admin_net = config_items[7]

    cleanup_machine(machine)
    configure_network(machine, client, net_bonding, admin_net)
    configure_system_disks(machine, os_raid, os_partitions)

    machine.refresh()
    user_data = build_user_data(machine, host_config, template)
    machine.deploy(distro_series=distro_name, user_data=user_data, hwe_kernel=kernel_version)
    print("Machine %s is now in %s state." % (hostname, machine.status._name_ ))

def release_machine(hostname, client):
    for machine in client.machines.list():
        if machine.hostname == hostname:
            break
    print("Releasing %s" % hostname)
    machine.release()



def main():

    parser = argparse.ArgumentParser(description='Configure and deploy machines present in MaaS.')
    parser.add_argument("machines_config", help="List of the machines with their configuration")
    parser.add_argument("-r", "--release", help="Release all machines on the list", action="store_true")
    args = parser.parse_args()

    yaml_config = yaml.load(open(args.machines_config))

    client = maas.client.connect(
        os.getenv("MAAS_API_URL"),
        apikey=os.getenv("MAAS_API_KEY")
    )

    if args.release:
        print("Are you sure you want release " + str(list(yaml_config.keys()))+"?")
        print("You are running this command on " + os.getenv("MAAS_API_URL"))
        print("Type 'I am sure I want this!' all in upper case to continue.")
        msg = sys.stdin.readline()
#        if msg == 'I AM SURE I WANT THIS!\n':
        if True:
            for hostname in yaml_config:
                release_machine(hostname, client)
        else:
            print("Confirmation failed.")
    else:
        for hostname in yaml_config:
            run_machine(hostname, yaml_config[hostname], client)

if __name__ == "__main__":
    main()

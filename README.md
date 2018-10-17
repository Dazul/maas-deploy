Maas-Deploy
===========

Maas deploy is used to configure and deploy bare-metal machines. It uses in input a yaml file containing the description of the machine we want to deploy. Maas-deploy uses an OS env variable with your API key. The variable is named MAAS_API_KEY.

Dependencies
------------

maas-deploy used python 3 to run. And the only dependency it has is with MAAS Client Library & CLI (python-libmaas). You can intall it with pip. Just run:

```console
pip install python-libmaas
```

For more about libmaas, visit: https://maas.github.io/python-libmaas/

Usage
-----

```console
export MAAS_API_URL=<Maas url>
export MAAS_API_KEY=<Private API key>

deploy.py my_fancy_machine.yaml
```

Description File
================

Each machine description starts always with the hostname of the machine. And everything else is child os that root item.

Then, various items can be defined:

* os
* os_raid1
* os_partitions
* net_bonding
* packages
* sources
* template

Each item, except the template item, can be defined into a template file. If an item is defined in the template and in the machine file, the version in the machine file will override the template one. If no item is define, maas default values will be applied.

Items
=====

os
--

OS we want to deploy on the node. The options here are the same as using the maas API. For example, use **xenial** for ubuntu 16.04 or **bionic** for ubuntu 18.04. Default value if not specifed is the MAAS default.


```yaml
os: bionic
```

os_raid1
--------

Only raid 1 for os disks is implemented yet. If the option is set, the entry **disks** will contain the list of disks to use on the raid cluster. If this item is not specified, the script will try to guess the 2 disks to use as system disks.

```yaml
os_raid1:
    disks:
        - sda
        - sdc
```

os_partitions
-------------

You can define a partition for the os_disks by declaring the mount point. Then, you define the size of the partition and the filesystem. Yet the size and filesystem is mandatory for each mount point, but the filesystem could be optional on future releases.

```yaml
os_partitions:
    /var:
        size: 20G
        filesystem: ext4
    /tmp:
        size: 20G
        filesystem: btrfs
    /boot:
        size: 1G
        filesystem: ext4
    /:
        size: 59G
        filesystem: xfs
    /home:
        size: 19G
        filesystem: ext4
```

net_bounding
------------

Net bounding has 3 parameters, two mandatory and one optional. Mandatory ones are slaves, which contains the network interface for the bond, and name, which will be the bond interface name.
You can attach vlans to the bound. The vlans numbers specified need to exist on MaaS.
For each vlan, you need to tell the name of the vlan as it exists on MaaS. All the others options are optional. But subnet need to exist on MaaS, and the IP need to exist on the particular subnet. default_gateway will ensure that the configuration attach to it will be the first to be configured.
Bond parameters are hard coded yet to `bond_mode="802.3ad"`, `bond_lacp_rate="fast"`, `bond_xmit_hash_policy="layer3+4"`.

```yaml
net_bonding:
    slaves:
        - enp4s0f0
        - enp4s0f1
    name: bond0
    vlans:
        mgmt:
            vlan: mgmt
            subnet: rack2:mgmt
            ip: 192.0.2.50
            default_gateway: true
            mtu: 9050
        vxlan:
            vlan: vxlan
```

packages
--------

You can list all the packages you want to be apt installed during the installation. Example with salt-minion package:

```yaml
packages:
    - salt-minion
```

sources
-------

If you want to use a personalized apt repository, you define it here, with the coresponding key. Example with saltstack repo:

```yaml
sources:
    saltstack:
        source: deb http://repo.saltstack.com/apt/ubuntu/16.04/amd64/latest $RELEASE main
        keyid: 754A1A7AE731F165D5E6D4BD0E08A149DE57BFBE
```

template
--------

```yaml
template: lab.yaml
```

unused_disks
------------

You can configure the non-os disks in two ways. As jbod_disks or as an disk_array.
For jbod_disks you need to provide the device, filesystem and mointpoint.
For disk_array you need to provide the array for cloud-init command, for example creating a raid. You can add a step2 to it if you want to create a volume group on the raid. For raid array that need a mount point, you can configure it with raid_array. Only Raid6 is supported yet.

Note that jbod_disks and raid_array will always be evaluated befor disk_array, and disk_array will apply on all disks that have neither be used on jbod_disks, raid_array nor os_raid1.

```yaml
unused_disks:
	jbod_disks:
        - device: /dev/sdc
          fs: ext4
          mountpoint: /data/01
        - device: /dev/sdd
          fs: ext4
          mountpoint: /data/02
    raid_array:
        disks:
            - sdc
            - sdd
            - sde
            - sdf
        fs: ext4
        mountpoint: /media/raid6_data
    disk_array:
         - cloud-init-per
         - once
         - softraid
         - mdadm
         - --create
         - /dev/md1
         - --level=6
         - --raid-devices=4
    step2:
        - cloud-init-per
        - once
        - b_volume-group
        - vgcreate
        - lxc
        - /dev/md1
```

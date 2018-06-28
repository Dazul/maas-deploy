Maas-Deploy
===========

Maas deploy is used to configure and deploy bare-metal machines. It uses in input a yaml file containing the description of the machine we want to deploy. Maas-deploy uses an OS env variable with your API key. The variable is named MAAS_API_KEY.

Usage
-----

export MAAS_API_KEY=123KEY456

deploy.py my_fancy_machine.yaml

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

```yaml
os: bionic
```

os_raid1
--------

```yaml
os_raid1:
    disks:
        - sda
        - sdc
```

os_partitions
-------------

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

```yaml
net_bonding:
    slaves:
        - enp4s0f0
        - enp4s0f1
    name: bond0
    vlans:
        br-mgmt: 2126
        br-storage: 2128
```

packages
--------

```yaml
packages:
    - salt-minion
```

sources
-------

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

Example
=======

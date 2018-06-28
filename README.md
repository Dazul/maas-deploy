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
-----



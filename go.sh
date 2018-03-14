#!/bin/sh
./deploy.py controller-dc1r02n01 11
./deploy.py controller-dc1r02n02 12
./deploy.py controller-dc1r02n03 13

./deploy.py storage-dc1r02n01 101
./deploy.py storage-dc1r02n02 102
./deploy.py storage-dc1r02n03 103
./deploy.py storage-dc1r02n04 104
./deploy.py storage-dc1r02n05 105

./deploy.py compute-dc1r02n01 51
./deploy.py compute-dc1r02n02 52
./deploy.py compute-dc1r02n03 53

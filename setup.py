#!/usr/bin/env python3

from setuptools import setup

setup(name='querierd',
      version=0.2,
      description='IGMP querier service',
      author='Marc Culler',
      url='http://github.com/culler/querierd/',
      packages=['querier'],
      install_requires=['netifaces>0.7']
     )

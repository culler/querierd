#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright© 2014 by Marc Culler and others.
# This file is part of QuerierD.
#
# QuerierD is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# QuerierD is distributed in the hope that it will be useful
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with QuerierD.  If not, see <http://www.gnu.org/licenses/>.

import os, sys, socket, time, struct, threading, syslog, signal
from .packets import *

version = '0.2'
__all__ = ['Querier']

all_routers = '224.0.0.1'
mdns_group = '224.0.0.251'

class Querier:
    """
    Sends an IGMP query packet at a specified time interval (in seconds).
    """
    def __init__(self, source_address, interval):
        if os.getuid() != 0:
            raise RuntimeError('You must be root to create a Querier.')
        self.source_address = source_address
        self.interval = interval
        self.socket = sock = socket.socket(socket.AF_INET,
                                           socket.SOCK_RAW,
                                           socket.IPPROTO_RAW)
        time.sleep(1) # Can't set options too soon (???)
        sock.settimeout(5)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
        sock.bind((source_address,0))
        self.build_query_packet()
        self.listener = None
        self.elected = True
        self.stop = False
        syslog.openlog('querierd')
        def sigterm_handler(signal, frame):
            self.stop = True
        signal.signal(signal.SIGTERM, sigterm_handler)
        
    def build_query_packet(self):
        igmp = IGMPv3Packet()
        igmp.type = 'query'
        igmp.max_response_time = 100

        self.packet = ip = IPv4Packet()
        ip.protocol = socket.IPPROTO_IGMP
        ip.ttl = 1
        ip.src = self.source_address
        ip.dst = all_routers
        ip.data = igmp.bytes()
    
    def run(self):
        syslog.syslog('Querier starting.')
        self.listener = QueryListener(self.source_address)
        while True:
            elapsed = self.listener.elapsed()
            if self.elected:
                self.socket.sendto(self.packet.bytes(), (all_routers, 0))
                if elapsed < self.interval:
                    self.elected = False
                    syslog.syslog('Lost querier election. Pausing.')
            else:
                if elapsed > 2*self.interval:
                    syslog.syslog('Won querier election. Resuming.')
                    self.elected = True
            if self.stop:
                break
            if not self.listener.thread.is_alive():
                syslog.syslog('Listener thread died.  Quitting.')
                sys.exit(1)
            time.sleep(self.interval)
        self.socket.close()
        syslog.syslog('Received SIGTERM.  Quitting.')
        sys.exit(0)

class QueryListener:
    """
    Manages the IGMP querier election process.  The elapsed() method returns
    the time since the last query packet from a higher priority device.
    """
    def __init__(self, address):
        self.address = self._ip_as_int(address)
        self._timestamp = 0 # the timestamp is shared data
        self.socket = sock = socket.socket(socket.AF_INET,
                                    socket.SOCK_RAW,
                                    socket.IPPROTO_IGMP)
        sock.bind(('224.0.0.1', 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.lock = threading.Lock()
        self.thread = thread = threading.Thread(target=self.listen)
        thread.daemon = True
        thread.start()

    def _ip_as_int(self, address):
        return struct.unpack("!I", socket.inet_aton(address))[0]
        
    def listen(self):
        while True:
            data, address = self.socket.recvfrom(65565)
            # make sure we got a query packet
            try:
                if data[20] == 17:
                    if self._ip_as_int(address[0]) < self.address:
                        self.lock.acquire()
                        self._timestamp = time.time()
                        self.lock.release()
            except IndexError:
                pass
    
    def elapsed(self):
        """
        Return the time elapsed since receiving a query from a
        device with a lower ip address.
        """
        self.lock.acquire()
        result = time.time() - self._timestamp
        self.lock.release()
        return result

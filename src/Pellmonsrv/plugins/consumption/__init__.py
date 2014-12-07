#! /usr/bin/python
# -*- coding: utf-8 -*-
"""
    Copyright (C) 2013  Anders Nylund

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

from Pellmonsrv.plugin_categories import protocols
from threading import Thread, Timer
from ConfigParser import ConfigParser
from os import path
import os, grp, pwd
import time
from datetime import datetime
from logging import getLogger
from time import mktime
from datetime import datetime
import subprocess
import simplejson as json
import re
from weakref import WeakValueDictionary
from random import randrange
import threading
from math import isnan

logger = getLogger('pellMon')

itemList=[{'name':'consumptionData24h',  'longname':'Consumption 24 hours',
           'type':'R',   'unit':'kg'   ,   'value':'0', 'min':'0', 'max':'-'},
          {'name':'consumptionData7d',  'longname':'Consumption 7 days',
           'type':'R',   'unit':'kg'   ,   'value':'0', 'min':'0', 'max':'-'},
          {'name':'consumptionData8w',  'longname':'Consumption 8 weeks',
           'type':'R',   'unit':'kg'   ,   'value':'0', 'min':'0', 'max':'-'},
          {'name':'consumptionData1y',  'longname':'Consumption 1 year',
           'type':'R',   'unit':'kg'   ,   'value':'0', 'min':'0', 'max':'-'},
         ]


class Consumption_plugin(protocols):
    class Bardata(object):
        def __init__(self, data):
            self.data = data
        def store_ref(self, ref):
                self.ref = ref
    def __init__(self):
        protocols.__init__(self)

    def activate(self, conf, glob):
        protocols.activate(self, conf, glob)
        self.db = self.glob['conf'].db
        self.totals=WeakValueDictionary()
        self.totals_fifo=[None]*200
        self.cache_lock = threading.Lock()

    def getItem(self, itemName):
        now=int(time.time())
        if itemName == 'consumptionData24h':
            align=now/3600*3600
            jsondata = self.barchartdata(start=align, period=3600, bars=24)
            return jsondata
        elif itemName == 'consumptionData7d':
            align=int(now)/86400*86400-(time.localtime(now).tm_hour-int(now)%86400/3600)*3600
            jsondata = self.barchartdata(start=align, period=3600*24, bars=7)
            return jsondata
        elif itemName == 'consumptionData8w':
            align=int(now+4*86400)/(86400*7)*(86400*7)-(time.localtime(now).tm_hour-int(now)%86400/3600)*3600 -4*86400
            jsondata = self.barchartdata(start=align, period=3600*24*7, bars=8)
            return jsondata
        elif itemName == 'consumptionData1y':
            align1y=now/int(31556952/12)*int(31556952/12)-(time.localtime(now).tm_hour-int(now)%86400/3600)*3600
            jsondata = self.barchartdata(start=align1y, period=3600*24*30, bars=12)
            return jsondata
        return 'Error'

    def getDataBase(self):
        return [item['name'] for item in itemList]

    def barchartdata(self, start=0, period=3600, bars=1):
        is_dst = time.daylight and time.localtime().tm_isdst > 0
        utc_offset = - (time.altzone if is_dst else time.timezone)
        try:
            period = int(period)
            start = int(start)
            bars = int(bars)
            now = int(time.time())
            if start==0:
                start = now
            bardata=[]
            total=0
            for i in range(bars)[::-1]:
                to_time = start - period*i
                from_time = to_time - period 
                try:
                    bar = float(self.rrd_total(from_time, to_time)[1:][:-1])
                    if isnan(bar):
                        bar = 0
                except Exception,e:
                    bar=0
                bardata.append([(from_time + utc_offset)*1000, bar])
                total += bar
            lastbar = float(self.rrd_total(start, now, cache=False)[1:][:-1])
            if isnan(lastbar):
                lastbar = 0
            if now-start > 100:
                predictedbar = (float(period) / (now-start)) * lastbar
            else:
                predictedbar = 0
            bardata_ = []
            bardata_.append( { 'label':'prediction', 'bars':{'barWidth':(now-start)*1000}, 'color':"#cdcdcd", 'data':[[(start+utc_offset)*1000, predictedbar]]} )
            bardata_.append( { 'label':'current', 'bars':{'barWidth':(now-start)*1000}, 'data':[[(start+utc_offset)*1000, lastbar]]} )
            bardata_.append( {'label':'last %u'%bars, 'data':bardata} ) 
            average = total / bars
            return json.dumps({'bardata':bardata_, 'total':total, 'average':average})
        except Exception, e:
            return str(e)

    def rrd_total(self, start, end, cache=True):
        start = str(start)
        end = str(end)
        with self.cache_lock:
            try:
                starts = self.totals[start]
                total = starts.data[end].data
            except Exception, e:
                command = ['rrdtool', 'graph', '--start', start, '--end', end,'-', 'DEF:a=%s:feeder_time:AVERAGE'%self.db,'DEF:b=%s:feeder_capacity:AVERAGE'%self.db, 'CDEF:c=a,b,*,360000,/', 'VDEF:s=c,TOTAL', 'PRINT:s:\"%.2lf\"']
                cmd = subprocess.Popen(command, shell=False, stdout=subprocess.PIPE)
                try:
                    total = cmd.communicate()[0].splitlines()[1]
                    if cache:
                        totalcontainer = self.Bardata(total)
                        try:
                            starts = self.totals[start]
                        except:
                            starts = self.Bardata(WeakValueDictionary())
                            #store a reference to the starts dict so it's not freed until empty
                            totalcontainer.store_ref(starts)
                            self.totals[start] = starts
                        starts.data[end] = totalcontainer
                        self.totals_fifo[randrange(0,len(self.totals_fifo))] = totalcontainer
                except Exception, e:
                    print 'asdasfd', str(e)
                    total = None
        if total:
            return total
        else:
            return None


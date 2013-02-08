#! /usr/bin/python
# -*- coding: iso-8859-15 -*-
"""
    Copyright (C) 2013  Anders Nylund

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import signal, os, time, Queue, serial, socket, threading, glib
from datetime import datetime
import dbus, dbus.service
from dbus.mainloop.glib import DBusGMainLoop
import gobject
import exceptions
import logging
import logging.handlers
from daemon import Daemon
import sys
from collections import namedtuple
import ConfigParser
from threading import Lock
import serial

# Publish an interface over the DBUS system bus
class MyDBUSService(dbus.service.Object):
	def __init__(self):
		bus=dbus.SystemBus()
		bus_name = dbus.service.BusName('org.pellmon.int', bus)
		dbus.service.Object.__init__(self, bus_name, '/org/pellmon/int')

	@dbus.service.method('org.pellmon.int')
	def GetItem(self, param):
		return getItem(param)

	@dbus.service.method('org.pellmon.int')
	def SetItem(self, param, value):
		return setItem(param, value)

	@dbus.service.method('org.pellmon.int')
	def GetDB(self):
		l=[]
		for item in dataBase:
			l.append(item)
		return l

def addCheckSum(s):
	x=0;
	logger.debug('addchecksum:')
	for c in s: x=x^ord(c)
	rs=s+chr(x)
	logger.debug(rs)
	return rs

def checkCheckSum(s):
	x=0;
	for c in s: 
		x=x^ord(c)
	return x
		
def pollThread():
	connected=False
	run=True
	
	while run:	
		commandqueue = q.get() 
		if commandqueue[0]==99:
			run=False
			continue

		if not connected:
#			try:	
#				logger.info("trying to connect")
#				srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#				srv.settimeout(1.0)
#				srv.connect( ('raspberrypi.local', 7777) )
#				connected=True
#				logger.info("Connected!")
#			except:
#				logger.info("connection failed")
#				continue
			connected=True

		# Write parameter/command		
		if commandqueue[0]==2:
			s=addCheckSum(commandqueue[1])
			#srv.sendall(s+"\r")
			logger.debug('serial write'+s)
			ser.write(s+'\r')	
			logger.debug('serial written'+s)		
			line=""
			try:
				#data=srv.recv(1024)
				line=str(ser.read(300))
				logger.debug('serial read'+line)
				#while data != '':
				#	line = line + data
				#	data=srv.recv(1024)
				#logger.info("No data, shut down socket")
				#connected=False
				#srv.shutdown(socket.SHUT_RDWR)
				#srv.close()
				#commandqueue[2].put(False)
				#continue
			except: #socket.timeout:
				logger.debug('Socket timeout, frame ready or empty')
			if line:
				commandqueue[2].put(line)
			else:
				commandqueue[2].put("No answer")
				logger.info('No answer')
		
		# Get frame
		if commandqueue[0]==3:
			responsequeue = commandqueue[2]
			sendFrame = addCheckSum(commandqueue[1].pollFrame)+"\r"
			logger.debug('sendFrame = '+sendFrame)
			logger.debug('serial write')
			ser.write(sendFrame+'\r')	
			logger.debug('serial written')	
			#srv.sendall(sendFrame)
			line=""
			try:
				#data=srv.recv(1024)
				line=str(ser.read(300))
				logger.debug('serial read'+line)
				#while data != '':
				#	line = line + data
				#	data=srv.recv(1024)
				#logger.info("No data, shut down socket")
				#connected=False
				#srv.shutdown(socket.SHUT_RDWR)
				#srv.close()
				#responsequeue.put(False)
				#continue
			except:# socket.timeout:
				logger.debug('Socket timeout, frame ready or empty')
			if line:	
				logger.debug('Got answer, parsing')	
				result=commandqueue[1].parse(line)
				try:
					logger.debug('Try to put parse result')
					responsequeue.put(result)
				except:
					logger.debug('command response queue put 1 fail')				
			else: 
				try:
					logger.debug('Try to put False, answer was empty')
					responsequeue.put(False)
				except:
					logger.debug('command response queue put 2 fail')				
				logger.info('Empty, no answer')

	logger.info("Pollthread end")

# Poll data and update the RRD database
def handlerThread():
		logger.debug('handlerTread started by signal handler')
		items=[]
		try:
			for data in pollData:
				items.append(getItem(data))
			s=':'.join(items)
			os.system("/usr/bin/rrdtool update "+db+" N:"+s)
			logger.setLevel(logging.INFO)
		except IOError as e:
			logger.setLevel(logging.DEBUG)
			logger.info('IOError: '+e.strerror)
			logger.info('   Trying Z01...')
			try:
				# I have no idea why, but every now and then the pelletburner stops answering, and this somehow causes it to start responding normally again
				getItem('oxygen_regulation')
			except IOError as e:
				logger.info('      failed '+e.strerror)

# Signal handler start handlerThread at regular interval
def handler(signum, frame):
	ht = threading.Thread(name='poll_thread', target=handlerThread)
	ht.start()
	
class Frame:
	def __init__(self, dd, frame):
		self.mutex=Lock()
		self.dataDef=dd	
		self.pollFrame=frame
		self.timestamp=0.0
		self.frameLength=0
		for i in self.dataDef:
			self.frameLength += i
		self.frameLength+=1
			
	def parse(self, s):
		logger.debug('Check checksum in parse '+s)
		if checkCheckSum(s):
			logger.info('Parse: checksum error on response message: ' + s)
			return False
		logger.debug('Checksum OK')
		if s==addCheckSum('E1'):
			logger.info('Parse: response message = E1, data does not exist')	
			return False
		if s==addCheckSum('E0'):
			logger.info('Parse: response message = E0, checksum fail')	
			return False						
		index=0
		self.data=[]	
		if self.frameLength == len(s):
			logger.debug('Correct length')
			self.mutex.acquire()
			self.timestamp=time.time()
			for i in self.dataDef:
				index2=index+i
				self.data.append(s[index:index2])
				index=index2
			self.mutex.release()
			logger.debug('Return True from parser')
			return True
		else:
			logger.info("Parse: wrong length " +len(s)+', expected '+self.frameLength)
			return False
		
	def get(self, index):
		self.mutex.acquire()
		data=self.data[index]
		self.mutex.release()
		return data

# Read data/parameter value
def getItem(param):	
		logger.debug('getitem')
		dataparam=dataBase[param]
		if hasattr(dataparam, 'frame'):
			ok=True
			# If the frame containing this data hasn't been read recently do it now
			if time.time()-dataparam.frame.timestamp > 5.0:
				try:
					responseQueue = Queue.Queue(3)
					try:  # Send "read parameter value" message to pollThread
						q.put((3,dataparam.frame,responseQueue))
						try:  # and wait for a response					
							ok=responseQueue.get(True, 5)
						except:
							ok=False
							logger.info('GetItem: Response timeout')
					except:
						ok=False
						logger.info('Getitem: MessageQueue full')
				except:
					logger.info('Getitem: Create responsequeue failed') 
					ok=False
			if (ok):
				if dataparam.decimals == -1: # not a number, return as is
					return dataparam.frame.get(dataparam.index)
				else:
					try:
						formatStr="{:0."+str(dataparam.decimals)+"f}"
						return  formatStr.format( float(dataparam.frame.get(dataparam.index)) / pow(10, dataparam.decimals)  )
					except:
						raise IOError(0, "Getitem result is not a number")
			else:
				raise IOError(0, "GetItem failed")
		else: 
			raise IOError(0, "A command can't be read")	

# Write a parameter/command	 
def setItem(param, s):
	dataparam=dataBase[param]
	if hasattr(dataparam, 'address'):
		try:
			value=float(s)
		except:
			return "not a number"
		if hasattr(dataparam, 'frame'):
			# Indicate that this frame has old data now
			dataparam.frame.timestamp = 0.0
		if hasattr(dataparam, 'decimals'):
			decimals = dataparam.decimals
		else:
			decimals = 0

		if value >= dataparam.min and value <= dataparam.max:
			s=("{:0>4.0f}".format(value * pow(10, decimals)))
			# Send "write parameter value" message to pollThread
			responseQueue = Queue.Queue() 
			q.put((2,dataparam.address + s, responseQueue))
			return responseQueue.get()
		else:
			return "Expected value "+str(dataparam.min)+".."+str(dataparam.max)
	else:
		return 'Not a setting value'


#***************************************************

class MyDaemon(Daemon):
	def run(self):
		logger.info('starting pelletMonitor')

		# Create 10s periodic signal handler
		signal.signal(signal.SIGALRM, handler)
		logger.info('created signalhandler')
		signal.setitimer(signal.ITIMER_REAL,2,10)
		logger.info('started timer')
		
		# Create RRD database
		if not os.path.exists(db):
			os.system(RrdCreateString)
	
		# Create and start poll_thread
		POLLTHREAD = threading.Thread(name='poll_thread', target=pollThread)
		POLLTHREAD.start()

		# Execute glib main loop to serve DBUS connections
		DBUSMAINLOOP.run()
		
		# glib main loop has quit
		logger.info("end")


#########################################################################################

# Create global stuff


parser = ConfigParser.ConfigParser()

# Load the configuration file
parser.read('pellmon.conf')

# These are read from the serial bus every 10 second
polldata = parser.items("pollvalues")
pollDataDict = {}
pollData = []
for key, value in polldata:
	pollDataDict[key] = value
	pollData.append(value)
	
# The RRD database which is updated every 10 second
db = parser.get('conf', 'database') 

# create logger
logger = logging.getLogger('pellMon')
loglevel = parser.get('conf', 'loglevel')
loglevels = {'info':logging.INFO, 'debug':logging.DEBUG}
try:
	logger.setLevel(loglevels[loglevel])
except:
	logger.setLevel(logging.DEBUG)

# create file handler which logs even debug messages
fh = logging.handlers.WatchedFileHandler(parser.get('conf', 'logfile'))
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.info('loglevel: '+loglevel)
# message queue, used to send frame polling commands to pollThread
q = Queue.Queue(3)

# 'FrameXXX' defines the serial bus frame format
# [list of character count per value], 'string with the frame address'
FrameZ00 = Frame([5,5,5,5,5,5,5,10,10,5,5,5,5,5,5,5,5,5],'Z000000')
FrameZ01 = Frame([5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5], 'Z010000')
FrameZ02 = Frame([10,10,10,10],'Z020000')
FrameZ03 = Frame([5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5],'Z030000')
FrameZ04 = Frame([5,5],'Z040000')
FrameZ05 = Frame([5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5],'Z050000')
FrameZ06 = Frame([5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5],'Z060000')

# 'param' type is for setting values that can be read and written
# 'data' type is for read-only measurement values
# 'command' type is for write-only data
param 	= namedtuple(  'param', 'frame index length decimals address min  max') 
data 	= namedtuple(   'data', 'frame index length decimals') 
command	= namedtuple('command',                             'address min  max')

# The 'dataBase'
global dataBase
dataBase = 	{
	'power':				data (FrameZ00, 0 ,  5,     0),
	'power_kW':				data (FrameZ00, 1 ,  5,     1),
	'boiler_temp':			data (FrameZ00, 2,   5,     1),	
	'chute_temp':			data (FrameZ00, 3 ,  5,     0),
	'smoke_temp':			data (FrameZ00, 4 ,  5,     0),
	'oxygen':				data (FrameZ00, 5 ,  5,     1),
	'light':				data (FrameZ00, 6 ,  5,     0),
	'feeder_time':			data (FrameZ00, 7 ,  5,     0),
	'ignition_time':		data (FrameZ00, 8 ,  5,     0),
	'alarm':				data (FrameZ00, 9 ,  5,     0),	
	'oxygen_desired':		data (FrameZ00, 11 , 5,     1),	
	'mode':					data (FrameZ00, 16,  5,     0),			
	'model':				data (FrameZ00, 17,  5,     0),			
	'motor_time':			data (FrameZ02, 0 ,  10,    0),
	'el_time':				data (FrameZ02, 1 ,  10,    0),
	'motor_time_perm':		data (FrameZ02, 2 ,  10,    0),
	'el_time_perm':			data (FrameZ02, 3 ,  10,    0),
	'ignition_count':		data (FrameZ03, 8 ,  5,     0),
	'version':				data (FrameZ04, 1,   5,    -1),

	'blower_low': 			param(FrameZ01, 0,   5,     0,       'A00',   4,  50),
	'blower_high': 			param(FrameZ01, 1,   5,     0,       'A01',   5, 100),
	'blower_mid': 			param(FrameZ03, 14,  5,     0,       'A06',   5,  75),
	'blower_cleaning':		param(FrameZ01,  4,  5,     0,       'A04',  25, 200),
	'boiler_temp_set':	 	param(FrameZ00, 10,  5,     0,       'B01',  40,  85),
	'boiler_temp_min':	 	param(FrameZ01,  9,  5,     0,       'B03',  10,  70),
	'feeder_low':	 		param(FrameZ01, 10,  5,     2,       'B04', 0.5,  25),
	'feeder_high':	 		param(FrameZ01, 11,  5,     1,       'B05',   1, 100),
	'feed_per_minute':		param(FrameZ01, 12,  5,     0,       'B06',   1,   3),

	'boiler_temp_diff_up':	param(FrameZ01, 17,  5,     0,       'C03',   0,  20),
	'boiler_temp_diff_down':param(FrameZ03, 13,  5,     0,       'C04',   0,  15),

	'light_required':		param(FrameZ01, 22,  5,     0,       'D03',   0, 100),

	'oxygen_regulation':	param(FrameZ01, 23,  5,     0,       'E00',   0,   2),
	'oxygen_low':			param(FrameZ01, 24,  5,     1,       'E01',  10,  19),
	'oxygen_high':			param(FrameZ01, 25,  5,     1,       'E02',   2,  12),
	'oxygen_gain': 			param(FrameZ01, 26,  5,     2,       'E03',   0,  99.99),

	'feeder_capacity_min': 	param(FrameZ01, 27,  5,     0,       'F00', 400,2000),
	'feeder_capacity':		param(FrameZ00, 12,  5,     0,       'F01', 400,8000),
	'feeder_capacity_max': 	param(FrameZ01, 29,  5,     0,       'F02', 400,8000),

	'chimney_draught':		param(FrameZ00, 13,  5,     0,       'G00',   0,  10),
	'chute_temp_max':		param(FrameZ01, 31,  5,     0,       'G01',  50,  90),
	'regulator_P':			param(FrameZ01, 32,  5,     1,       'G02',   1,  20),
	'regulator_I':			param(FrameZ01, 33,  5,     2,       'G03',   0,   5),
	'regulator_D':			param(FrameZ01, 34,  5,     1,       'G04',   1,  50),
	'blower_corr_low': 		param(FrameZ01, 39,  5,     0,       'G05',  50, 150),
	'blower_corr_high':		param(FrameZ01, 40,  5,     0,       'G06',  50, 150),
	'cleaning_interval':	param(FrameZ01, 41,  5,     0,       'G07',   1, 120),
	'cleaning_time':		param(FrameZ01, 42,  5,     0,       'G08',   0,  60),
	'language':				param(FrameZ04, 0,   5,     0,       'G09',   0,   3),

	'autocalculation':		param(FrameZ03, 10,  5,     0,       'H04',   0,   1),
	'time_minutes':			param(FrameZ01, 44,  5,     0,       'H07',   0,1439),

	'oxygen_corr_10':		param(FrameZ03, 1,   5,     0,       'I00',   0, 100),
	'oxygen_corr_50':		param(FrameZ03, 2,   5,     0,       'I01',   0, 100),
	'oxygen_corr_100':		param(FrameZ03, 3,   5,     0,       'I02',   0, 100),
	'oxygen_corr_interval':	param(FrameZ03, 4,   5,     0,       'I03',   1,  60),
	'oxygen_regulation_P':	param(FrameZ03, 5,   5,     2,       'I04',   0,   5),
	'oxygen_regulation_D':	param(FrameZ03, 6,   5,     0,       'I05',   0, 100),
	'blower_off_time':		param(FrameZ03, 9,   5,     0,       'I07',   0,  30),

	'comp_clean_interval': 	param(FrameZ05, 18,  5,     0,       'L00',   0,  21),
	'comp_clean_time': 		param(FrameZ05, 19,  5,     0,       'L01',   0,  10),
	'comp_clean_blower':	param(FrameZ05, 20,  5,     0,       'L02',   0, 100),
	'comp_clean_wait': 		param(FrameZ05, 29,  5,     0,       'L03',   0, 300),

	'blower_corr_mid': 		param(FrameZ05, 22,  5,     0,       'M00',  50, 150),

	'min_power':			param(FrameZ01, 37,  5,     0,       'H02',  10, 100),
	'max_power':			param(FrameZ01, 38,  5,     0,       'H03',  10, 100),
	'burner_off':			command(                             'V00',   0,   0),
	'burner_on': 			command(                             'V01',   0,   0),
	'reset_alarm': 			command(                             'V02',   0,   0)
}	

# Build a command string to create the rrd database
RrdCreateString="rrdtool create "+db+" --step 10 "
for item in pollData:
	RrdCreateString=RrdCreateString+"DS:%s:GAUGE:60:U:U " % item	
RrdCreateString=RrdCreateString+"RRA:AVERAGE:0,999:1:20000 \
RRA:AVERAGE:0,999:10:20000 \
RRA:AVERAGE:0,999:100:20000 \
RRA:AVERAGE:0,999:1000:20000"

# Open serial port
ser = serial.Serial()
ser.port     = parser.get('conf', 'serialport') 
ser.baudrate = 9600
ser.parity   = 'N'
ser.rtscts   = False
ser.xonxoff  = False
ser.timeout  = 1		
try:
	ser.open()
except serial.SerialException, e:
	logger.info("Could not open serial port %s: %s\n" % (ser.portstr, e))
logger.info('serial port ok')
# DBUS needs the gobject main loop, this way it seems to work...
gobject.threads_init()
dbus.mainloop.glib.threads_init()    
DBUSMAINLOOP = gobject.MainLoop()
DBusGMainLoop(set_as_default=True)
myservice = MyDBUSService()

if __name__ == "__main__":


	daemon = MyDaemon('/tmp/pelletMonitor.pid')
	if len(sys.argv) == 2:
		if 'start' == sys.argv[1]:
			daemon.start()
		elif 'stop' == sys.argv[1]:
			daemon.stop()
		elif 'restart' == sys.argv[1]:
			daemon.restart()
		else:
			print "Unknown command"
			sys.exit(2)
			sys.exit(0)
	else:
		print "usage: %s start|stop|restart" % sys.argv[0]
		sys.exit(2)



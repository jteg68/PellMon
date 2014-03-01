# -*- coding: utf-8 -*-
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

from threading import Lock
from logging import getLogger
import time
import Queue
import threading
import serial
from enumerations import dataEnumerations
logger = getLogger('pellMon')

class Protocol(threading.Thread):
    """Provides read/write functions for parameters/measurement data
    for a bio comfort pellet burner connected through rs232"""

    def __init__(self, device, version_string):
        """Initialize the protocol and database according to given version"""
        self.dummyDevice=False
        if device == None:
            self.dummyDevice=True
            self.dataBase = self.createDataBase('6.99')
            return
        # Open serial port
        s = serial.Serial()
        s.port     = device
        s.baudrate = 9600
        s.parity   = 'N'
        s.rtscts   = False
        s.xonxoff  = False
        s.timeout  = 1
        try:
            s.open()
        except serial.SerialException, e:
            logger.info("Could not open serial port %s: %s\n" % (device, e))
            self.dummyDevice=True
            self.dataBase = self.createDataBase('6.99')
            return
        logger.info('serial port ok')
        self.ser = s

        # message queue, used to send frame polling commands to pollThread
        self.q = Queue.Queue(300)
        self.dataBase = self.createDataBase('0000')

        # Create and start poll_thread
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self.start()

        if version_string == 'auto':
            try:
                version_string = self.getItem('version').lstrip()
                logger.info('chip version detected as: %s'%version_string)
            except:
                version_string = '0.0'
                logger.info('version detection failed')
        else:
            logger.info('chip version from config: %s'%version_string)
        self.dataBase = self.createDataBase(version_string)

    def getDataBase(self):
        return self.dataBase

    def getItem(self, param):
        import random
        try:
            dataparam=self.dataBase[param]
            return str(random.randint(dataparam.min, dataparam.max))
        except:
            return str(random.randint(0, 999))

        if self.dummyDevice:
            return '1234'
        """Read data/parameter value"""
        logger.debug('getitem')
        dataparam=self.dataBase[param]
        if hasattr(dataparam, 'frame'):
            ok=True
            # If the frame containing this data hasn't been read recently
            # or if the specific index has been written after the frame was last read
            # or if the specific index has just been written (might still give old value when read
            # so a retry should do a new poll)
            # then re-read
            writeTime = dataparam.frame.indexWriteTime[dataparam.index]
            readTime = dataparam.frame.readtime
            if time.time()-readTime > 8.0 or writeTime>readTime or time.time()-writeTime < 4.0:
                try:
                    responseQueue = Queue.Queue(3)
                    try:  # Send "read parameter value" message to pollThread
                        if writeTime>readTime or time.time()-writeTime < 4.0:
                            self.q.put(("FORCE_GET", dataparam.frame,responseQueue))
                        else:
                            self.q.put(("GET", dataparam.frame,responseQueue))
                        try:  # and wait for a response
                            ok=responseQueue.get(True, 5)
                        except:
                            ok=False
                            logger.debug('GetItem: Response timeout')
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
                    value = dataparam.frame.get(dataparam.index)
                    try:
                        return dataEnumerations[param][int(value)]
                    except:
                        try:
                            formatStr="{:0."+str(dataparam.decimals)+"f}"
                            return  formatStr.format( float(value) / pow(10, dataparam.decimals)  )
                        except:
                            raise IOError(0, "Getitem result is not a number")
            else:
                raise IOError(0, "GetItem failed")
        else:
            raise IOError(0, "A command can't be read")

    def setItem(self, param, s):
        return 'OK'
        if self.dummyDevice:
            return 'OK'

        """Write a parameter/command"""
        dataparam=self.dataBase[param]
        if hasattr(dataparam, 'address'):
            try:
                try:
                    value=float(s)
                except:
                    return "not a number"
                if hasattr(dataparam, 'frame'):
                    # Save time when this index was written
                    dataparam.frame.indexWriteTime[dataparam.index] = time.time()
                if hasattr(dataparam, 'decimals'):
                    decimals = dataparam.decimals
                else:
                    decimals = 0

                if value >= dataparam.min and value <= dataparam.max:
                    s=("{:0>4.0f}".format(value * pow(10, decimals)))
                    # Send "write parameter value" message to pollThread
                    responseQueue = Queue.Queue()
                    self.q.put(("PUT", dataparam.address + s, responseQueue))
                    response = responseQueue.get()
                    if response == addCheckSum('OK'):
                        logger.info('Parameter %s = %s'%(param,s))
                        response = 'OK'
                    return response
                else:
                    return "Expected value "+str(dataparam.min)+".."+str(dataparam.max)
            except Exception, e:
                return e
        else:
            return 'Not a setting value'

    def createDataBase(self, version_string):
        """return a dictionary of parameters supported on version_string"""
        from datamap import dataBaseMap
        db={}
        for param_name in dataBaseMap:
            mappings = dataBaseMap[param_name]
            for supported_versions in mappings:
                if version_string >= supported_versions[0] and version_string < supported_versions[1]:
                    db[param_name] = mappings[supported_versions]
        return db

    def run(self):
        """Run as thread. Waits on queue self.q for frame read / parameter write commands, responds in an
        other queue received with the command"""
        logger.debug('thred run')
        while True:
            commandqueue = self.q.get()
            logger.debug('got command')
            # Write parameter/command
            if commandqueue[0]=="PUT":
                s=addCheckSum(commandqueue[1])
                logger.debug('serial write'+s)
                self.ser.flushInput()
                self.ser.write(s+'\r')
                logger.debug('serial written'+s)
                line=""
                try:
                    line=str(self.ser.read(3))
                    logger.debug('serial read'+line)
                except:
                    logger.debug('Serial read error')
                if line:
                    # Send back the response
                    commandqueue[2].put(line)
                else:
                    commandqueue[2].put("No answer")
                    logger.info('No answer')

            # Get frame command
            if commandqueue[0]=="GET" or commandqueue[0]=="FORCE_GET":
                responsequeue = commandqueue[2]
                frame = commandqueue[1]
                # This frame could have been read recently by a previous queued read request, so check again if it's necessary to read
                if time.time()-frame.readtime > 8.0 or commandqueue[0]=="FORCE_GET":
                    sendFrame = addCheckSum(frame.pollFrame)+"\r"
                    logger.debug('sendFrame = '+sendFrame)
                    line=""
                    try:
                        self.ser.flushInput()
                        logger.debug('serial write')
                        self.ser.write(sendFrame+'\r')
                        logger.debug('serial written')
                        line=str(self.ser.read(frame.getLength()))
                        logger.debug('serial read'+line)
                    except:
                        logger.debug('Serial read error')
                    result = False
                    if line:
                        logger.debug('Got answer, parsing')
                        result=commandqueue[1].parse(line)
                        if result:
                            try:
                                responsequeue.put(result)
                            except:
                                logger.debug('command response queue put 1 fail')
                    else:
                        logger.debug('Timeout')
                    if not result:
                        logger.debug('Retrying')
                        try:
                            self.ser.flushInput()
                            logger.debug('serial write')
                            self.ser.write(sendFrame+'\r')
                            logger.debug('serial written')
                            line=str(self.ser.read(frame.getLength()))
                            logger.debug('answer: '+line)
                        except:
                            logger.debug('Serial read error')
                        if line:
                            logger.debug('Got answer, parsing')
                            result=commandqueue[1].parse(line)
                            try:
                                responsequeue.put(result)
                            except:
                                logger.debug('command response queue put 1 fail')
                        else:
                            try:
                                logger.debug('Try to put False, answer was empty')
                                responsequeue.put(False)
                            except:
                                logger.debug('command response queue put 2 fail')
                            logger.info('Timeout again, give up and return fail')
                else:
                    responsequeue.put(True)


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

class Frame:
    """Handle parsing of response strings to the different frame formats, and
    provide thread safe get data function"""

    def __init__(self, dd, frame):
        self.mutex=Lock()
        self.dataDef=dd
        self.pollFrame=frame
        self.readtime=0.0
        self.indexWriteTime = [0.0]*len(self.dataDef)
        self.frameLength=0
        for i in self.dataDef:
            self.frameLength += i
        #include checksum byte
        self.frameLength+=1

    def getLength(self):
        return self.frameLength

    def parse(self, s):
        logger.debug('Check checksum in parse '+s)
        if checkCheckSum(s):
            logger.debug('Parse: checksum error on response message: ' + s)
            return False
        logger.debug('Checksum OK')
        if s==addCheckSum('E1'):
            logger.debug('Parse: response message = E1, data does not exist')
            return False
        if s==addCheckSum('E0'):
            logger.debug('Parse: response message = E0, checksum fail')
            return False
        index=0
        self.data=[]
        if self.frameLength == len(s):
            logger.debug('Correct length')
            self.mutex.acquire()
            self.readtime=time.time()
            logger.debug("reset readtime")
            for i in self.dataDef:
                index2=index+i
                self.data.append(s[index:index2])
                index=index2
            self.mutex.release()
            logger.debug('Return True from parser')
            return True
        else:
            logger.debug("Parse: wrong length "+str(len(s))+', expected '+str(self.frameLength))
            return False

    def get(self, index):
        self.mutex.acquire()
        data=self.data[index]
        self.mutex.release()
        return data



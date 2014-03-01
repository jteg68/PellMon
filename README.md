PellMon
=======

PellMon is logging, monitoring and configuration solution for pellet burners. It consists of a backend server daemon, which
uses RRDtool as a logging database, and a frontend daemon providing a responsive mobile friendly web based user interface. 
Additionally there is a command line tool for interfacing with the server. PellMon can communicate directly with a supported
pellet burner, or it can use a feeder-auger revolution counter as base for pellet consumption calculation.

PellMon uses plugins to provide data about your burner. The most fully featured plugin is ScotteCom, which enables communication 
with a NBE scotte/woody/biocomfort V4, V5 or V6 pellet burner. It gives you access to almost all configuration parameters 
and measurement data, and also handles logging of alarms and mode/setting changes.

The plugin system makes it easy to add custom plugins for extended functionality, a 'template' plugin is provided as an example
along with the other preinstalled plugins:

PelletCalc. Provides a calculated power value and pellet consumption from a feeder auger counter.

RaspberryPi. Gives access to inputs and outputs on the raspberry pi single board computer. One input can be configured
as a counter to provide a base for pellet consumption calculation. It also provides general I/O, and a tachometer input that can be used
to measure the blower speed, by interfacing to the blowers tacho output or by using an optical detector.

OWFS. Communicates with an owserver, and can be used to read onewire sensors, for instance temperature. It can also use a 
onewire input (ds2460 based) to count feeder auger revolutions for use with the PelletCalc plugin. 

CustomAlarms. Create an unlimited number of limits to watch on available data, optionally send email when a limit is exceeded.

Calculate. Provides editable expressions that calcualates new values based on the existing data.

SiloLevel. Uses rrdtool to calculate and graph the pellet silo level from the fill-up time to current time. 

Plugin decumentation is int the configuration file.

####Contains:

###pellmonsrv.py:
Communication daemon. Implements a DBUS interface for reading and writing setting values and reading of measurement data. Optionally handles logging of measurement data to an RRD database. 
<pre>
usage: pellmonsrv.py [-h] [-P PIDFILE] [-U USER] [-G GROUP] [-C CONFIG] [-D {SESSION,SYSTEM}] [-p PLUGINDIR]
                  {debug,start,stop,restart}

positional arguments:
  {debug,start,stop,restart}
                        With debug argument pellmonsrv won't daemonize

optional arguments:
  -h, --help            show this help message and exit
  -P PIDFILE, --PIDFILE PIDFILE
                        Full path to pidfile
  -U USER, --USER USER  Run as USER
  -G GROUP, --GROUP GROUP
                        Run as GROUP
  -C CONFIG, --CONFIG CONFIG
                        Full path to config file
  -D {SESSION,SYSTEM}, --DBUS {SESSION,SYSTEM}
                        which bus to use, SESSION is default
  -p PLUGINDIR, --PLUGINDIR PLUGINDIR
                        Full path to plugin directory
</pre>

###pellmonweb.py:
Webserver and webapp, plotting of measurement, calculated consumption and data and parameter reading/writing.
<pre>
usage: pellmonweb.py [-h] [-D] [-P PIDFILE] [-U USER] [-G GROUP] [-C CONFIG] [-d {SESSION,SYSTEM}]

optional arguments:
  -h, --help            show this help message and exit
  -D, --DAEMONIZE       Run as daemon
  -P PIDFILE, --PIDFILE PIDFILE
                        Full path to pidfile
  -U USER, --USER USER  Run as USER
  -G GROUP, --GROUP GROUP
                        Run as GROUP
  -C CONFIG, --CONFIG CONFIG
                        Full path to config file
  -d {SESSION,SYSTEM}, --DBUS {SESSION,SYSTEM}
                        which bus to use, SESSION is default
</pre>
###pellmoncli.py:

Interactive command line client with tab completion. Reading and writing of setting values, and reading of measurement data.
<pre>
usage: pellmoncli.py [-h] {get,set,list,i}
</pre>

###pellmon.conf
Configuration values. 


##User installation:
    # Generate configure script
    ./autogen.sh
    # Configure for installation in home directory
    ./configure --prefix=/home/<user>/.local
    make
    make install
    # Start the daemons manually
    /home/<user>/.local/bin/pellmonsrv.py -C /home/<user>/.local/etc/pellmon/pellmon.conf start
    /home/<user>/.local/bin/pellmonweb.py -C /home/<user>/.local/etc/pellmon/pellmon.conf -D
    # Stop the daemons manually
    kill $(cat /tmp/pellmonsrv.pid)
    kill $(cat /tmp/pellmonweb.pid)
###Uninstall
    make uninstall


##System installation:
    # Add system users
    sudo adduser --system --group --no-create-home pellmonsrv
    sudo adduser --system --group --no-create-home pellmonweb
    # Give the server access to the serial port
    sudo adduser pellmonsrv dialout
    ./autogen.sh
    # Configure for running as system users
    ./configure --with-user_srv=pellmonsrv --with-user_web=pellmonweb --sysconfdir=/etc
    make
    sudo make install
    # Activate pellmon dbus system bus permissions
    sudo service dbus reload
    # Start the daemons manually
    sudo service pellmonsrv start
    sudo service pellmonweb start
    # Or add them to init so they are started at boot
    sudo update-rc.d pellmonsrv defaults
    sudo update-rc.d pellmonweb defaults
###Uninstall
    sudo make uninstall
    # Remove from init if you added them
    sudo update-rc.d pellmonsrv remove
    sudo update-rc.d pellmonweb remove
    
##Dependencies:
<pre>
rrdtool, python-serial, python-cherrypy3, python-dbus, python-mako, python-gobject, python-simplejson
</pre>

##Build dependencies:
<pre>
autoconf
</pre>


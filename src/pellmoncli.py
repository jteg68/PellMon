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
import readline, os
import sys
import argparse
from gi.repository import Gio, GLib

# Handles tab completion with input_raw
def complete(text, state):
    completerTexts=COMMANDS
    line = readline.get_line_buffer()
    splitline = line.split()
    if splitline:
        if line.startswith('get ') or line.startswith('g '):
            completerTexts=db
        elif line.startswith('set ') or line.startswith('s '):
            completerTexts=db
        else:
            completerTexts=COMMANDS
    for cmd in completerTexts:
        if cmd.startswith(text):
            if not state:
                return cmd+' '
            else:
                state -= 1

def getItem(itm):
    try:
    	return notify.GetItem('(s)',itm)
    except:
        return "error"

def setItem(item, value):
    try:
        return notify.SetItem('(ss)',item, value)
    except:
        return "error"
    
def getdb():
    return notify.GetDB()

def getItemCli(args):
    for item in args.item:
        print getItem(item)

def setItemCli(args):
    print setItem(args.item, args.value)

def getdbCli(args):
    l = notify.GetDB()
    print "\n".join(l)

def cli(args):
    # Get list of data/parameters
    global db
    db=getdb()
    global COMMANDS
    COMMANDS = ['get', 'set', 'quit']
    completerTexts=COMMANDS
    # Sets up readline for tab completion
    readline.parse_and_bind("tab: complete")
    readline.set_completer(complete)

    run=True
    while run:
        try:
            a=raw_input(">")
            l=a.split()
            if len(l)==2:
                if l[0] in ['get', 'g']:
                    if l[1] == "all":
                        for item in db:
                            try:
                                print item, getItem(item)
                            except:
                                pass
                    else:
                        if l[1] in db:
                            try:
                                print getItem(l[1])
                            except:
                                print "dbus error"
                        else:
                            print l[1]+" is not a data/parameter name "
            elif len(l)==3:
                if l[0] in ['set', 's']:
                    if l[1] in db:
                        print setItem(l[1], l[2])
                    else:
                        print l[1]+" is not a parameter/command name"
            elif len(l)==1:
                if l[0] in ['quit','q']:
                    run=False
        except KeyboardInterrupt:
            run=False
    
if __name__ == "__main__":

    # Connect to pellmonsrv on the dbus system bus
    d = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    notify = Gio.DBusProxy.new_sync(d, 0, None, 'org.pellmon.int', '/org/pellmon/int', 'org.pellmon.int', None)
    version=getItem('pellmonsrv_version')
    if version == 'error':
        # if that fails try the session bus instead
        e = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        notify = Gio.DBusProxy.new_sync(e, 0, None, 'org.pellmon.int', '/org/pellmon/int', 'org.pellmon.int', None)

    # create the top-level parser
    parser = argparse.ArgumentParser(prog='pellmoncli')

    subparsers = parser.add_subparsers(help='sub-command help')

    # create the parser for the "get" command
    parser_a = subparsers.add_parser('get', help='read item value')
    parser_a.add_argument('item', nargs='+', help='name of the item to read')
    parser_a.set_defaults(func=getItemCli)

    # create the parser for the "set" command
    parser_b = subparsers.add_parser('set', help='write item value')
    parser_b.add_argument('item', help='name of the item to write')
    parser_b.add_argument('value', help='value to write')
    parser_b.set_defaults(func=setItemCli)

    # create the parser for the "list" command
    parser_c = subparsers.add_parser('list', help='list all items')
    parser_c.set_defaults(func=getdbCli)

    # create the parser for the "interactive" option
    parser_d = subparsers.add_parser('i', help='enter interactive mode')
    parser_d.set_defaults(func=cli)

    # parse arguments and run function according to command 
    args = parser.parse_args()
    args.func(args)



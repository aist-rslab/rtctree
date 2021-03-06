# -*- Python -*-
# -*- coding: utf-8 -*-

'''rtctree

Copyright (C) 2009-2014
    Geoffrey Biggs
    RT-Synthesis Research Group
    Intelligent Systems Research Institute,
    National Institute of Advanced Industrial Science and Technology (AIST),
    Japan
    All rights reserved.
Licensed under the Eclipse Public License -v 1.0 (EPL)
http://www.opensource.org/licenses/eclipse-1.0.txt

File: ports.py

Objects representing ports and connections.

Do not create port objects directly. Call the parse_port function, which will
create the correct type of port object automatically.

'''


import RTC
import threading

from rtctree.exceptions import *
from rtctree.utils import build_attr_string, dict_to_nvlist, nvlist_to_dict


##############################################################################
## API functions

def parse_port(port_obj, owner):
    '''Create a port object of the correct type.

    The correct port object type is chosen based on the port.port_type
    property of port_obj.

    @param port_obj The CORBA PortService object to wrap.
    @param owner The owner of this port. Should be a Component object or None.
    @return The created port object.

    '''
    profile = port_obj.get_port_profile()
    props = nvlist_to_dict(profile.properties)
    if props['port.port_type'] == 'DataInPort':
        return DataInPort(port_obj, owner)
    elif props['port.port_type'] == 'DataOutPort':
        return DataOutPort(port_obj, owner)
    elif props['port.port_type'] == 'CorbaPort':
        return CorbaPort(port_obj, owner)
    else:
        return Port(port_obj, owner)


##############################################################################
## Base port object

class Port(object):
    '''Base class representing a port of a component.

    Do not create Port objects directly. Call parse_port().

    '''
    def __init__(self, port_obj=None, owner=None, *args, **kwargs):
        '''Base port constructor.

        @param port_obj The CORBA PortService object to wrap.
        @param owner The owner of this port. Should be a Component object or
                     None.

        '''
        super(Port, self).__init__(*args, **kwargs)
        self._obj = port_obj
        self._connections = None
        self._owner = owner
        self._mutex = threading.RLock()
        self._parse()

    def connect(self, dests=[], name=None, id='', props={}):
        '''Connect this port to other ports.

        After the connection has been made, a delayed reparse of the
        connections for this and the destination port will be triggered.

        @param dests A list of the destination Port objects. Must be provided.
        @param name The name of the connection. If None, a suitable default
                    will be created based on the names of the two ports.
        @param id The ID of this connection. If None, one will be generated by
               the RTC implementation.
        @param props Properties of the connection. Required values depend on
                     the type of the two ports being connected.
        @raises IncompatibleDataPortConnectionPropsError, FailedToConnectError

        '''
        with self._mutex:
            if self.porttype == 'DataInPort' or self.porttype == 'DataOutPort':
                for prop in props:
                    if prop in self.properties:
                        if props[prop] not in [x.strip() for x in self.properties[prop].split(',')] and \
                                'any' not in self.properties[prop].lower():
                            # Invalid property selected
                            raise IncompatibleDataPortConnectionPropsError
                    for d in dests:
                        if prop in d.properties:
                            if props[prop] not in [x.strip() for x in d.properties[prop].split(',')] and \
                                    'any' not in d.properties[prop].lower():
                                # Invalid property selected
                                raise IncompatibleDataPortConnectionPropsError
            if not name:
                name = self.name + '_'.join([d.name for d in dests])
            props = dict_to_nvlist(props)
            profile = RTC.ConnectorProfile(name, id,
                    [self._obj] + [d._obj for d in dests], props)
            return_code, profile = self._obj.connect(profile)
            if return_code != RTC.RTC_OK:
                raise FailedToConnectError(return_code)
            self.reparse_connections()
            for d in dests:
                d.reparse_connections()

    def disconnect_all(self):
        '''Disconnect all connections to this port.'''
        with self._mutex:
            for conn in self.connections:
                self.object.disconnect(conn.id)
            self.reparse_connections()

    def get_connection_by_dest(self, dest):
        '''DEPRECATED. Search for a connection between this and another port.'''
        with self._mutex:
            for conn in self.connections:
                if conn.has_port(self) and conn.has_port(dest):
                    return conn
            return None

    def get_connections_by_dest(self, dest):
        '''Search for all connections between this and another port.'''
        with self._mutex:
            res = []
            for c in self.connections:
                if c.has_port(self) and c.has_port(dest):
                    res.append(c)
            return res

    def get_connections_by_dests(self, dests):
        '''Search for all connections involving this and all other ports.'''
        with self._mutex:
            res = []
            for c in self.connections:
                if not c.has_port(self):
                    continue
                for d in dests:
                    if not c.has_port(d):
                        continue
                res.append(c)
            return res

    def get_connection_by_id(self, id):
        '''Search for a connection on this port by its ID.'''
        with self._mutex:
            for conn in self.connections:
                if conn.id == id:
                    return conn
            return None

    def get_connection_by_name(self, name):
        '''Search for a connection to or from this port by name.'''
        with self._mutex:
            for conn in self.connections:
                if conn.name == name:
                    return conn
            return None

    def reparse(self):
        '''Reparse the port.'''
        self._parse()
        self.reparse_connections()

    def reparse_connections(self):
        '''Reparse the connections this port is involved in.'''
        with self._mutex:
            self._connections = None

    @property
    def connections(self):
        '''A list of connections to or from this port.

        This list will be created at the first reference to this property.
        This means that the first reference may be delayed by CORBA calls,
        but others will return quickly (unless a delayed reparse has been
        triggered).

        '''
        with self._mutex:
            if not self._connections:
                self._connections = [Connection(cp, self) \
                                     for cp in self._obj.get_connector_profiles()]
        return self._connections

    @property
    def is_connected(self):
        '''Check if this port is connected to any other ports.'''
        with self._mutex:
            if self.connections:
                return True
            return False

    @property
    def name(self):
        '''The name of this port.'''
        with self._mutex:
            return self._name

    @property
    def object(self):
        '''The PortService object that represents the port.'''
        with self._mutex:
            return self._obj

    @property
    def owner(self):
        '''This port's owner (usually a Component object).'''
        with self._mutex:
            return self._owner

    @property
    def porttype(self):
        '''The type of port this is.

        Valid values are any class that @ref parse_port can create.

        '''
        return self.__class__.__name__

    @property
    def properties(self):
        '''Properties of the port.'''
        with self._mutex:
            return self._properties

    def _parse(self):
        # Parse the PortService object to build a port profile.
        with self._mutex:
            profile = self._obj.get_port_profile()
            self._name = profile.name
            self._properties = nvlist_to_dict(profile.properties)
            if self.owner:
                prefix = self.owner.instance_name + '.'
                if self._name.startswith(prefix):
                    self._name = self._name[len(prefix):]


##############################################################################
## Data port objects

class DataPort(Port):
    '''Specialisation of the Port class for data ports.

    Do not create DataPort objects directly. Call parse_port().

    '''
    def __init__(self, port_obj=None, owner=None, *args, **kwargs):
        '''DataPort constructor.

        @param port_obj The CORBA PortService object to wrap.
        @param owner The owner of this port. Should be a Component object or
                     None.

        '''
        super(DataPort, self).__init__(port_obj=port_obj, owner=owner, *args,
                                       **kwargs)

    def connect(self, dests=[], name=None, id='', props={}):
        '''Connect this port to other DataPorts.

        After the connection has been made, a delayed reparse of the
        connections for this and the destination port will be triggered.

        @param dests A list of the destination Port objects. Must be provided.
        @param name The name of the connection. If None, a suitable default
                    will be created based on the names of the two ports.
        @param id The ID of this connection. If None, one will be generated by
               the RTC implementation.
        @param props Properties of the connection. Suitable defaults will be
                     set for required values if they are not already present.
        @raises WrongPortTypeError

        '''
        # Data ports can only connect to opposite data ports
        with self._mutex:
            new_props = props.copy()
            ptypes = [d.porttype for d in dests]
            if self.porttype == 'DataInPort':
                if 'DataOutPort' not in ptypes:
                    raise WrongPortTypeError
            if self.porttype == 'DataOutPort':
                if 'DataInPort' not in ptypes:
                    raise WrongPortTypeError
            if 'dataport.dataflow_type' not in new_props:
                new_props['dataport.dataflow_type'] = 'push'
            if 'dataport.interface_type' not in new_props:
                new_props['dataport.interface_type'] = 'corba_cdr'
            if 'dataport.subscription_type' not in new_props:
                new_props['dataport.subscription_type'] = 'new'
            if 'dataport.data_type' not in new_props:
                new_props['dataport.data_type'] = \
                        self.properties['dataport.data_type']
            super(DataPort, self).connect(dests=dests, name=name, id=id,
                                          props=new_props)


class DataInPort(DataPort):
    '''Specialisation of the DataPort class for input ports.

    Do not create DataInPort objects directly. Call parse_port().

    '''
    pass


class DataOutPort(DataPort):
    '''Specialisation of the DataPort class for output ports.

    Do not create DataOutPort objects directly. Call parse_port().

    '''
    pass


##############################################################################
## CORBA port objects

class CorbaPort(Port):
    '''Specialisation of the Port class for service ports.

    Do not create CorbaPort objects directly. Call parse_port().

    '''
    def __init__(self, port_obj=None, owner=None, *args, **kwargs):
        '''CorbaPort constructor.

        @param port_obj The CORBA PortService object to wrap.
        @param owner The owner of this port. Should be a Component object or
                     None.

        '''
        super(CorbaPort, self).__init__(port_obj=port_obj, owner=owner,
                                        *args, **kwargs)
        self._interfaces = None

    def connect(self, dests=None, name=None, id='', props={}):
        '''Connect this port to other CorbaPorts.

        After the connection has been made, a delayed reparse of the
        connections for this and the destination port will be triggered.

        @param dests A list of the destination Port objects. Must be provided.
        @param name The name of the connection. If None, a suitable default
                    will be created based on the names of the two ports.
        @param id The ID of this connection. If None, one will be generated by
               the RTC implementation.
        @param props Properties of the connection. Suitable defaults will be
                     set for required values if they are not already present.
        @raises WrongPortTypeError, MismatchedInterfacesError,
                MismatchedPolarityError

        '''
        with self._mutex:
            # Corba ports can only connect to corba ports of the opposite
            # polarity
            for d in dests:
                if not d.porttype == 'CorbaPort':
                    raise WrongPortTypeError
            # Check the interfaces and their respective polarities match
            if self.interfaces:
                for d in dests:
                    if not d.interfaces:
                        raise MismatchedInterfacesError
                for intf in self.interfaces:
                    for d in dests:
                        match = d.get_interface_by_instance_name(
                                    intf.instance_name)
                        if not match:
                            raise MismatchedInterfacesError
                        if intf.polarity == match.polarity:
                            # Polarity should be opposite
                            raise MismatchedPolarityError
            else:
                for d in dests:
                    if d.interfaces:
                        raise MismatchedInterfacesError
            # Make the connection
            new_props = props.copy()
            if 'port.port_type' not in new_props:
                new_props['port.port_type'] = 'CorbaPort'
            super(CorbaPort, self).connect(dests=dests, name=name, id=id,
                                           props=new_props)

    def get_interface_by_instance_name(self, name):
        '''Get an interface of this port by instance name.'''
        with self._mutex:
            for intf in self.interfaces:
                if intf.instance_name == name:
                    return intf
            return None

    @property
    def interfaces(self):
        '''The list of interfaces this port provides or uses.

        This list will be created at the first reference to this property.
        This means that the first reference may be delayed by CORBA calls,
        but others will return quickly (unless a delayed reparse has been
        triggered).

        '''
        with self._mutex:
            if not self._interfaces:
                profile = self._obj.get_port_profile()
                self._interfaces = [SvcInterface(intf) \
                                    for intf in profile.interfaces]
        return self._interfaces


##############################################################################
## Service port interface object

class SvcInterface(object):
    '''Object representing the interface used by a service port.'''
    def __init__(self, intf_obj=None, *args, **kwargs):
        '''Constructor.

        @param intf_obj The CORBA PortInterfaceProfile object to wrap.

        '''
        super(SvcInterface, self).__init__(*args, **kwargs)
        self._obj = intf_obj
        self._mutex = threading.RLock()
        self._parse()

    def polarity_as_string(self, add_colour=True):
        '''Get the polarity of this interface as a string.

        @param add_colour If True, ANSI colour codes will be added to the
                          string.
        @return A string describing the polarity of this interface.

        '''
        with self._mutex:
            if self.polarity == self.PROVIDED:
                result = 'Provided', ['reset']
            elif self.polarity == self.REQUIRED:
                result = 'Required', ['reset']
            if add_colour:
                return build_attr_string(result[1], supported=add_colour) + \
                        result[0] + build_attr_string('reset',
                                supported=add_colour)
            else:
                return result[0]

    def reparse(self):
        '''Reparse the interface object.'''
        self._parse()

    @property
    def instance_name(self):
        '''Instance name of the interface.'''
        with self._mutex:
            return self._instance_name

    @property
    def polarity(self):
        '''Polarity of this interface.'''
        with self._mutex:
            return self._polarity

    @property
    def polarity_string(self):
        '''The polarity of this interface as a coloured string.'''
        with self._mutex:
            return self.polarity_as_string()

    @property
    def type_name(self):
        '''Type name of the interface.'''
        with self._mutex:
            return self._type_name

    def _parse(self):
        # Parse the PortInterfaceProfile object.
        with self._mutex:
            self._instance_name = self._obj.instance_name
            self._type_name = self._obj.type_name
            if self._obj.polarity == RTC.PROVIDED:
                self._polarity = self.PROVIDED
            else:
                self._polarity = self.REQUIRED

    ## Constant for provided interface polarity.
    PROVIDED = 1
    ## Constant for required interface polarity.
    REQUIRED = 2


##############################################################################
## Connection object

class Connection(object):
    '''An object representing a connection between two or more ports.'''
    def __init__(self, conn_profile_obj=None, owner=None, *args, **kwargs):
        '''Constructor.

        @param conn_profile_obj The CORBA ConnectorProfile object to wrap.
        @param owner The owner of this connection. If the creator of this
                     object is not a Port object (or derivative thereof), this
                     value should be set to None.

        '''
        super(Connection, self).__init__(*args, **kwargs)
        self._obj = conn_profile_obj
        self._owner = owner
        self._mutex = threading.RLock()
        self._parse()

    def __str__(self):
        return 'Connection {0} (ID: {1}), properties {2}, with ports '\
            '{3}'.format(self._name, self._id, self._properties, self._ports)

    def disconnect(self):
        '''Disconnect this connection.'''
        with self._mutex:
            if not self.ports:
                raise NotConnectedError
            # Some of the connection participants may not be in the tree,
            # causing the port search in self.ports to return ('Unknown', None)
            # for those participants. Search the list to find the first
            # participant that is in the tree (there must be at least one).
            p = self.ports[0][1]
            ii = 1
            while not p and ii < len(self.ports):
                p = self.ports[ii][1]
                ii += 1
            if not p:
                raise UnknownConnectionOwnerError
            p.object.disconnect(self.id)

    def has_port(self, port):
        '''Return True if this connection involves the given Port object.

        @param port The Port object to search for in this connection's ports.

        '''
        with self._mutex:
            for p in self.ports:
                if not p[1]:
                    # Port owner not in tree, so unknown
                    continue
                if port.object._is_equivalent(p[1].object):
                    return True
            return False

    def reparse(self):
        '''Reparse the connection.'''
        self._parse()

    @property
    def id(self):
        '''The ID of the connection.'''
        with self._mutex:
            return self._id

    @property
    def name(self):
        '''The name of the connection.'''
        with self._mutex:
            return self._name

    @property
    def owner(self):
        '''This connection's owner, if created by a Port object.'''
        with self._mutex:
            return self._owner

    @property
    def ports(self):
        '''The list of ports involved in this connection.

        The result is a list of tuples, (port name, port object). Each port
        name is a full path to the port (e.g. /localhost/Comp0.rtc:in) if
        this Connection object is owned by a Port, which is in turn owned by
        a Component in the tree. Otherwise, only the port's name will be used
        (in which case it will be the full port name, which will include the
        component name, e.g. 'ConsoleIn0.in'). The full path can be used to
        find ports in the tree.

        If, for some reason, the owner node of a port cannot be found, that
        entry in the list will contain ('Unknown', None). This typically means
        that a component's name has been clobbered on the name server.

        This list will be created at the first reference to this property.
        This means that the first reference may be delayed by CORBA calls,
        but others will return quickly (unless a delayed reparse has been
        triggered).

        '''
        def has_port(node, args):
            if node.get_port_by_ref(args):
                return node
            return None

        with self._mutex:
            if not self._ports:
                self._ports = []
                for p in self._obj.ports:
                    # My owner's owner is a component node in the tree
                    if self.owner and self.owner.owner:
                        root = self.owner.owner.root
                        owner_nodes = [n for n in root.iterate(has_port,
                                args=p, filter=['is_component']) if n]
                        if not owner_nodes:
                            self._ports.append(('Unknown', None))
                        else:
                            port_owner = owner_nodes[0]
                            port_owner_path = port_owner.full_path_str
                            port_name = p.get_port_profile().name
                            prefix = port_owner.instance_name + '.'
                            if port_name.startswith(prefix):
                                port_name = port_name[len(prefix):]
                            self._ports.append((port_owner_path + ':' + \
                                port_name, parse_port(p, self.owner.owner)))
                    else:
                        self._ports.append((p.get_port_profile().name,
                                            parse_port(p, None)))
        return self._ports

    @property
    def properties(self):
        '''The connection's properties dictionary.'''
        with self._mutex:
            return self._properties

    def _parse(self):
        # Parse the ConnectorProfile object.
        with self._mutex:
            self._name = self._obj.name
            self._id = self._obj.connector_id
            self._ports = None
            self._properties = nvlist_to_dict(self._obj.properties)


# vim: tw=79


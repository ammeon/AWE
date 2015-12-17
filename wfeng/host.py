"""Module represents the classes as read from the hostfile
@copyright: Ammeon Ltd
"""
from lxml import etree

import logging
from wfeng import constants

LOG = logging.getLogger(__name__)


class Hosts(object):
    """Set of hosts to be used for workflow"""
    def __init__(self):
        """Initialises hosts"""
        self.hosts = {}

    def parse(self, filename):
        """Parses filename to produce dictionary of hosts where key of
           dictionary is host type

           Args:
               filename: Name of XML hosts file
           Returns:
               boolean: True if parsed correctly
        """
        schema_file = constants.HOSTS_XSD
        xmlschema_doc = etree.parse(schema_file)
        xmlschema = etree.XMLSchema(xmlschema_doc)
        try:
            doc = etree.parse(filename)
            xmlschema.assertValid(doc)
            LOG.debug("Succesfully validated {0}".format(filename))
            tree = etree.parse(filename)
            root = tree.getroot()
            if root.tag != "hosts":
                err_msg = "Root is not hosts: {0}".format(root.tag)
                LOG.error(err_msg)
                return False
            for element in root.iterchildren(tag=etree.Element):
                if element.tag == "host":
                    servertype = element.get("server")
                    if servertype not in self.hosts:
                        LOG.log(constants.TRACE, "Creating type {0}".format(\
                                servertype))
                        self.hosts[servertype] = []
                    hostname = element.get("name")
                    host_ip = element.get("ip")
                    username = element.get("username")
                    if self.host_exists(hostname):
                        LOG.error("Duplicate host {0}/{1}".format(hostname,
                                                                servertype))
                        return False
                    else:
                        self.hosts[servertype].append(\
                                   Host(hostname, host_ip, username,
                                        servertype))
                else:
                    err_msg = "Tag is not host {0}".format(element.tag)
                    LOG.error(err_msg)
                    return False
            # Now parsed file add myself to list
            # NB.We need a way of accessing by hostname and also
            # by index
            self.hosts[constants.LOCAL] = []
            self.hosts[constants.LOCAL].append(Host(constants.LOCAL, "", "",
                                               ""))
            return True
        except Exception as err:
            err_msg = "Failed to validate {0} against {1}: {2}".format(
                            filename, schema_file, repr(err))
            LOG.error(err_msg)
            LOG.debug(err_msg, exc_info=True)
            return False

    def host_exists(self, hostname):
        """ Returns whether hostname already specified """
        found_server = False
        for _, hostlist in self.hosts.iteritems():
            # where hostlist is list of Host objects
            for host in hostlist:
                if hostname == host.hostname:
                    found_server = True
        return found_server

    def get_types(self):
        """ Returns a list of server types"""
        types = []
        for servertype, _ in self.hosts.iteritems():
            LOG.log(constants.TRACE, "Found type {0}".format(servertype))
            if servertype != constants.LOCAL:
                types.append(servertype)
        return types

    def get(self, hostname, htype):
        """ Returns the Host object that matches hostname and type """
        if htype in self.hosts:
            hosts = self.hosts[htype]
        else:
            hosts = []
        obj = None
        i = 0
        while obj == None and i < len(hosts):
            if hosts[i].hostname == hostname:
                obj = hosts[i]
            i = i + 1
        if obj == None:
            LOG.debug("Failed to find {0}/{1}".format(hostname, htype))
        return obj


class Host(object):
    """ Represents single host"""
    def __init__(self, hostname, ipaddr, username, servertype):
        self.hostname = hostname
        self.ipaddr = ipaddr
        self.username = username
        self.servertype = servertype
        self.params = {}

    def add_params(self, params):
        """ Add all params from params to self.params """
        for key, val in params.iteritems():
            self.params[key] = val

    def add_param(self, name, value, override=False):
        """ Adds parameter found from running task on this host. Does nothing
            if value is None

            Args:
                name: name of parameter
                value: value of parameter
            Returns:
                boolean: True if added ok,
                False if failed to add (param already in dictionary with
                different value, and override not True)

        """
        if value == None:
            return True
        dname = name.lstrip().strip()
        dvalue = value.lstrip().strip()
        if not override:
            if dname in self.params and dvalue != self.params[dname]:
                return False
        self.params[dname] = dvalue
        return True

    def equals(self, host):
        """ Compares this Host with that described by host, and
            returns if they are the same. Ignores the parameters which are
            dynamic and added later

            Args:
                host: Host to compare against
            Returns:
                boolean: True if same, ignoring parameters (as these are
                populated at runtime).
                False if different

        """
        if self.hostname != host.hostname:
            LOG.debug("Hosts differ {0}/{1}".format(self.hostname,
                                                   host.hostname))
            return False
        if self.ipaddr != host.ipaddr:
            LOG.debug("IPs differ {0}/{1}".format(self.ipaddr, host.ipaddr))
            return False
        if self.servertype != host.servertype:
            LOG.debug("Types differ {0}/{1}".format(self.servertype,
                       host.servertype))
            return False
        if self.username != host.username:
            LOG.debug("Username differ {0}/{1}".format(self.username,
                                                       host.username))
            return False
        return True

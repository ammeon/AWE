""" Holds utility functions
@copyright: Ammeon Ltd
"""
from wfeng import constants
import threading
import time
import re
import os

INFO_FORMAT = "  -->{0}{1}{4}: {2} {3}\n"
ERR_FORMAT = "  -->{0}{1}{4}: {5}{2}{6} {3}\n"


def get_boolean(child, attributename):
    """ Reads a boolean as a string from an XML element and converts to
        Boolean """
    attstr = child.get(attributename)
    if attstr == "true":
        attvalue = True
    else:
        attvalue = False
    return attvalue


def get_stringtoboolean(strIn):
    """ converts a string to a boolean
        Arguments:
            strIn: the string for conversion
        Returns:
            False if value is None or lowercase of strIn is "false,
            True if lowercase of strIn is "true", else None
    """
    if strIn is None:
        return False
    lcase = strIn.lower()
    if lcase == "true":
        return True
    elif lcase == "false":
        return False
    else:
        return None


def populate_boolean(element, value, attributename):
    if value:
        element.attrib[attributename] = "true"
    else:
        element.attrib[attributename] = "false"
    return


def populate_optional(element, value, attributename):
    """ Updates XML element with value if its not None """
    if value != None:
        element.attrib[attributename] = value
    return


def populate_dictionary(element, valuedict, attributename):
    """ Writes contents of dictionary as comma separated key=value string"""
    attval = ""
    if valuedict != None:
        for key, value in valuedict.iteritems():
            commaval = ""
            if len(attval) != 0:
                # Add comma if not first
                commaval = ","
            attval = "{0}{1}{2}={3}".format(attval, commaval, key, value)
    if len(attval) > 0:
        element.attrib[attributename] = attval
    return


def get_dictionary(child, attributename):
    """ Reads a dictionary as a comma separated key=value string from an XML
        element and converts to dictionary """
    dictval = {}
    attstr = child.get(attributename)
    if attstr == None:
        return dictval
    vars = attstr.split(',')
    for var in vars:
        varname, varvalue = var.split('=')
        dictval[varname] = varvalue
    return dictval


def processLineForTags(line, infoprefixes, errprefixes, log, tid, output_level,
                             host_colour):
    """ Checks line for info and err lines, and logs accordingly.
        Returns:
            True: if logged
            False: if not logged
    """
    # They are written to logs already, so this is just analysing what
    # needs to go additionally to screen
    newcolour = host_colour
    endcolour = constants.Colours.END
    if newcolour == endcolour:
        # No need to change colour
        newcolour = ""
        endcolour = ""
    for infoprefix in infoprefixes:
        if infoprefix in line:
            if output_level >= constants.ERROR_INFO:
                infoline = line.split(infoprefix, 1)[1].lstrip().strip()
                log.log(constants.INFONOTIME,
                         INFO_FORMAT.format(newcolour, tid, infoprefix,
                               infoline, endcolour))
                return True
    for errprefix in errprefixes:
        if errprefix in line:
            if output_level >= constants.ERROR_ONLY:
                errline = line.split(errprefix, 1)[1].lstrip().strip()
                log.log(constants.ERRORNOTIME,
                         ERR_FORMAT.format(newcolour, tid, errprefix,
                              errline, endcolour,
                              constants.Colours.status[constants.FAILED],
                              constants.Colours.END))
                return True
    return False


def replace_vars(cmd, params):
    """ Replace any occurance of $VAR in cmd, with its value in params if
        one present. Returns string with replacement."""
    fullcmd = ""
    args = cmd.split(" ")
    for arg in args:
        if arg.startswith("$"):
            param = arg[1:]
            if param in params:
                fullcmd = fullcmd + params[param]
            else:
                fullcmd = fullcmd + arg
        else:
            fullcmd = fullcmd + arg
        fullcmd = fullcmd + " "
    fullcmd = fullcmd.strip()
    return fullcmd


def is_number(str_val):
    """ Returns whether str_val is of format <number>[.<number>]*
            Returns:
                True if number
    """
    regexp = "^[0-9][\.0-9]*$"
    if re.match(regexp, str_val):
        return True
    else:
        return False


def check_version(version_req, current_version, exact_match=True):
    """ Returns whether host is already at required_version
        Returns:
            True if current_version >= version_req
    """
    if current_version == None:
        return False
    if version_req == None:
        return True
    if current_version == version_req:
        return True
    # If version is of format num.num then can compare with greater/less
    # than logic, otherwise cannot compare so will just compare by
    # exact match only
    if not is_number(current_version) or \
       not is_number(version_req):
        return False
    # If not matched and want exact_match then return False now
    if exact_match:
        return False
    # Split by .
    current_vers = current_version.split(".")
    req_vers = version_req.split(".")
    # Will loop checking values of each sub-part, so as to cope with
    # comparing 2.1.1 to 2.2, will loop which ever is shorter
    num_loops = len(current_vers)
    if len(req_vers) < num_loops:
        num_loops = len(req_vers)
    # Now go through each index
    for index in range(num_loops):
        if int(current_vers[index]) < int(req_vers[index]):
            # Current is less than required, so return False
            return False
        elif int(current_vers[index]) > int(req_vers[index]):
            # Current is greater than required, so return True
            return True
        # else we are at same, so need to go onto next index to compare
    # So so far we are at the same version, but that might mean we have
    # compared 2.1.1 with 2.1 so still need more checks
    if len(current_vers) > len(req_vers):
        # We were same until stopped checking, but current has more
        # values then required, e.g. 2.1.1 compared to 2.1, so return True
        return True
    elif len(req_vers) > len(current_vers):
        # We were same until stopped checking, but required has more
        # values then required, e.g. 2.1 compared to 2.1.1, so return False
        return False
    else:
        # We must be exact match!
        return True


def logSkippedTask(logger, task, hoststr):
    if task.status in constants.SUCCESS_STATUSES:
        durationstr = ""
        if task.actualDuration != None:
            durationstr = " DURATION: {0}".format(task.actualDuration)
        logger.info("{0}SKIP_{5}{1} TASK {2}: {3}{4}{6}\n".format(
             constants.COLOURS.status[task.status],
             constants.COLOURS.END, task.getId(),
             task.getCmd(),
             hoststr, task.status, durationstr))
    else:
        logger.info("{0}SKIPPED{1} TASK {2}: {3}{4}\n".format(
                constants.COLOURS.status[task.status],
                constants.COLOURS.END, task.getId(),
                task.getCmd(),
                hoststr))


def getStatusCount(status, taskname, log):
    """ Returns tuple of success, failed, skipped which corresponds to
        status value """
    numSuccess = 0
    numFailed = 0
    numSkipped = 0
    if status in constants.SUCCESS_STATUSES:
        log.log(constants.TRACE, "Success {0} {1}".format(status, taskname))
        numSuccess = 1
    elif status == constants.FAILED:
        log.log(constants.TRACE, "Failed {0}".format(taskname))
        numFailed = 1
    elif status == constants.SKIPPED:
        log.log(constants.TRACE, "Skipped {0}".format(taskname))
        numSkipped = 1
    else:
        log.log(constants.TRACE,
                "Unexpected status {0} for {1}".format(status,
                                                       taskname))
    return (numSuccess, numFailed, numSkipped)


def digit_in_range(choice, max_val, min_val=1):
    """ Verifies choice is integer in range 1->max """
    if not choice.isdigit():
        return False
    else:
        val = int(choice)
        if val < min_val or val > max_val:
            return False
    return True


class SpinnerThread(threading.Thread):
    def __init__(self, outputfunc, add_space):
        super(SpinnerThread, self).__init__()
        self._stop = threading.Event()
        self.output_func = outputfunc
        self.add_space = add_space

    def stop(self):
        self._stop.set()

    def run(self):
        spinner_char = "/-\\|"
        if self.add_space:
            self.output_func(" ", writelog=False)
        while not self.stopped():
            for i in range(4):
                if not self.stopped():
                    self.output_func("%s\b" % spinner_char[i], writelog=False)
                    time.sleep(1)
                else:
                    break

    def stopped(self):
        return self._stop.isSet()


class StreamToLogger:
    """
    Fake file-like stream object that redirects writes to a logger
    """
    def __init__(self, prefix, username, ipaddr, infoprefixes, errprefixes,
                       output_level, host_colour, log):
        self.linebuf = ''
        self.prefix = prefix
        self.username = username
        self.ipaddr = ipaddr
        self.infoprefixes = infoprefixes
        self.errprefixes = errprefixes
        self.output_level = output_level
        self.host_colour = host_colour
        self.log = log

    def write(self, buf):
        lineToIgnore = "[{0}@{1}] out: ".format(self.username, self.ipaddr)
        line = buf.rstrip('\n')
        if line == lineToIgnore:
            # Only put in trace
            self.log.log(constants.TRACE, "%s:%s" % (self.prefix, line))
        # If we are sent a blank line we will still output it, but Fabric
        # itself sends blank lines, so use buf on "" instead of line
        elif buf == "":
            pass
        elif self._is_spinner(line):
            pass
        else:
            # Write to screen if info or err line
            if not processLineForTags(line, self.infoprefixes,
                                       self.errprefixes,
                                       self.log, self.prefix,
                                       self.output_level,
                                       self.host_colour):
                self.log.log(constants.DEBUGNOTIME, "  -->%s: %s" % \
                         (self.prefix, line))

    def _is_spinner(self, line):
        for i in range(len(constants.SPINNER_CHARS)):
            if line == constants.SPINNER_CHARS[i] + "\b":
                return True
            if line == constants.SPINNER_CHARS[i] + "\b\b":
                return True
            if line == constants.SPINNER_CHARS[i]:
                return True
        return False

    def flush(self):
        # Do not need to do anything
        return

    def close(self):
        # Do not need to do anything
        return


def get_file_less_ext(full_filename):
    """ Returns filename without extension"""
    dirs = full_filename.split("/")
    parts = dirs[len(dirs) - 1].split(".")
    if len(parts) == 1:
        filename = parts[0]
    else:
        filename = None
        for i in range(len(parts) - 1):
            if filename == None:
                filename = parts[i]
            else:
                filename = filename + "." + parts[i]
    return filename


def extractIniParam(iniparams, inStr):
    """ if inStr starts with $ then we return matching param from the ini
        params, otherwise return taskval
        Params:
        iniparams - the map of parameters derived from the ini file
        inStr - input string
    """
    taskval = inStr
    if inStr.startswith('$'):
        #find the param
        # note that this has been pre-validated, so we should not ever
        # actually fail to find the key
        param = inStr[1:]
        if param in iniparams:
            taskval = iniparams[param]
            if taskval == "":
                taskval = None
    return taskval


def getHostsThatApply(task, hosts, log):
    """ Returns list of hosts that this task applies to from those
        available """
    hostList = []
    if task.servertype not in hosts.hosts:
        # If its optional - just skip it, else raise error
        if task.optional:
            log.debug("Skipping %s as no server of type %s" %
                              (task.name, task.servertype))
            return hostList
        else:
            raise ValueError(
                   'Missing mandatory server %s in hosts file' % \
                   task.servertype)
    taskhosts = hosts.hosts[task.servertype]
    if task.hosts == constants.ALL:
        for y in taskhosts:
            hostList.append(y)
    else:
        notNum = False
        serverNum = task.hosts
        if task.hosts.startswith("!"):
            # hosts is format !1 to indicate all but first etc
            notNum = True
            serverNum = task.hosts[1:]
        if serverNum == "$":
            # $ indicates last host, so work out last host
            # Want all but last
            serverNum = len(taskhosts)
        else:
            serverNum = int(serverNum)
        if notNum:
            for i in range(len(taskhosts)):
                if (i + 1) != serverNum:
                    hostList.append(taskhosts[i])
        else:
            hostList.append(taskhosts[serverNum - 1])
    return hostList


def outputTitleLines(line, err_msg, term_size, hyphen_line):
        """ Clears page and outputs line in center with hyphens underneath"""
        os.system('clear')
        print line.center(term_size)
        print hyphen_line[:len(line)].center(term_size)
        print err_msg
        print ""

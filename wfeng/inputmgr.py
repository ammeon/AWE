"""Responsible for getting user input about whether to run tasks
@copyright: Ammeon Ltd
"""
import logging
import os
import constants
import wfconfig
import sys
import utils

SKIP_PROMPT = "Do you wish to run task (y), skip (s) or exit (n)?:\n"
SKIP_SERVER_PROMPT = "Do you wish to skip all tasks on server {0}(y/n)?:\n"
HOST_PROMPT = "Please enter {0} version of host {1}: \n"
HYPHEN_LINE = "---------------------------------------------------------------"

LOG = logging.getLogger(__name__)


class InputMgr(object):
    """Performs requests to get info from user as to whether to run
       commands"""

    def askRunSkipTask(self, task, excluded):
        """ Prompts user whether to run, skip task.
            Arguments:
                task: StatusTask to run
                excluded: Current list of servers to exclude, is updated
                          if user chooses to skip all tasks on this
                          server
            Returns:
                0 to run, 1 to skip, 2 to exit
        """
        ret_val = 0
        choice = ""
        while choice != "y" and choice != "n" and choice != "s":
            choice = raw_input(SKIP_PROMPT)
            if choice == "n":
                LOG.info("Stopping workflow as requested")
                ret_val = 2
            elif choice == "s":
                ret_val = 1
                # Now find out whether to skip all tasks on
                # this server
                for host in task.getHosts():
                    choice = ""
                    prompt = SKIP_SERVER_PROMPT.format(host.hostname)
                    while choice != "y" and choice != "n":
                        choice = raw_input(prompt)
                    if choice == "y":
                        excluded.append(host.hostname)
        return ret_val

    def askContinue(self, wfstatus):
        """Asks user whether to continue or not, details of question to ask
           are in wfstatus object.
           Arguments:
               wfstatus:  WorkflowStatus object with details of question
           Returns:
               True if should continue, False otherwise
        """
        run = True
        val = None
        while not wfstatus.isValidResponse(val):
            val = raw_input(wfstatus.user_msg)
            if wfstatus.isStopResponse(val):
                run = False
        return run

    def getVersion(self, htype, host):
        """ Asks user what version host is at
            Arguments:
                host:  Name of host to get version from
                htype: Type of version, software or OS
            Returns:
                Version entered
        """
        val = None
        while val == None:
            val = raw_input(HOST_PROMPT.format(htype, host))
        return val


class MenuMgr(object):
    """ Class that provides command line menu and gets input """

    def __init__(self, term_size, config):
        self.term_size = term_size
        self.config = config

    def getOptions(self, options, err_msg=""):
        """ Get menu options, and populate options object
            Arguments:
                options: WorkflowOptions
                err_msg: error message to display
            Returns:
                True if ok, False if should quit
        """
        self._outputTitleLines("WORKFLOW ENGINE", err_msg)
        # if we are using the menu then we cannot be using --list
        print " [1] Run display deployment"
        print " [2] Run pre-checks"
        print " [3] Run execute workflow"
        print " [4] Run post-checks"
        print " [5] Run single workflow task"
        print " [6] Run tagged set of tasks"
        print " [7] Edit Workflow Engine options"
        choice = raw_input("\nPlease select your option or q to quit:\n")
        if choice == "q":
            return False
        if not utils.digit_in_range(choice, 7):
            return self.getOptions(options, "Invalid option {0}".\
                                               format(choice))
        val = int(choice)
        if val == 1:
            options.phase = constants.OPT_DISPLAY
            return self.getMenuPhase(options)
        elif val == 2:
            options.phase = constants.OPT_PRECHECK
            return self.getMenuPhase(options)
        elif val == 3:
            options.phase = constants.OPT_EXECUTE
            return self.getMenuPhase(options)
        elif val == 4:
            options.phase = constants.OPT_POSTCHECK
            return self.getMenuPhase(options)
        elif val == 5:
            options.task = self.getMenuSingleTask()
            options.phase = constants.OPT_POSTCHECK
            return self.getMenuSingleTaskServers(options,
                                  "task {0}".format(options.task))
        elif val == 6:
            # TODO: If run tag should also run postcheck or not by default?
            options.phase = constants.OPT_EXECUTE
            return self.getMenuTag(options)
        elif val == 7:
            self.getEditMenu(options)
            # Re-display menu as done editing
            return self.getOptions(options)

    def getMenuPhase(self, options, err_msg=""):
        """ Displays sub-menu to determine whether to run phase on
            all servers, servers of particular type, single server"""
        return self.getMenuServers(options,
                                    "{0} phase".format(options.phase),
                                    err_msg)

    def getMenuServers(self, options, desc, err_msg=""):
        """ Displays sub-menu to determine whether to run on
            all servers, servers of particular type, single server.
            Used when running phase or tagged set"""
        self._outputTitleLines("WORKFLOW ENGINE - {0}".format(desc),
                               err_msg)
        # if we are using the menu then we cannot be using --list
        print " [1] Run {0} on all servers".format(desc)

        print " [2] Run {0} on all servers of selected type".format(desc)

        print " [3] Run {0} on single server".format(desc)
        choice = raw_input("\nPlease select your option or q to quit:\n")
        if choice == "q":
            return False
        if not utils.digit_in_range(choice, 3):
            return self.getMenuServers(options, desc,
                                        "Invalid option {0}".format(choice))
        val = int(choice)
        LOG.debug("Requesting further details for {0}".\
                               format(desc))
        if val == 1:
            options.servertype = constants.ALL
            options.servername = constants.ALL
        elif val == 2:
            options.servername = constants.ALL
            options.servertype = self.getMenuServerType(options)
        elif val == 3:
            options.servername = self.getMenuSingleServer(desc)
            options.servertype = constants.ALL
        if val == 1 or val == 2:
            # Check if want to exclude server
            if options.exclude == None:
                options.exclude = self.getExcludeServers(options,
                                                         desc)
        return True

    def getMenuServerType(self, options, err_msg=""):
        """ Display menu for choosing a server type """
        LOG.debug("Getting server type for phase {0}".format(options.phase))
        self._outputTitleLines("WORKFLOW ENGINE - {0}".format(options.phase),
                  err_msg)
        # TODO: Improve by showing them the choice of server types
        # in the workflow
        choice = raw_input("\nEnter type of server to use\n")
        return choice

    def getMenuSingleServer(self, info, err_msg=""):
        """ Display menu for choosing a single server"""
        LOG.debug("Getting server name for {0}".format(info))
        self._outputTitleLines("WORKFLOW ENGINE - {0}".format(info), err_msg)
        # TODO: Improve by showing them the choice of servers in the workflow
        name = raw_input("\nEnter name of server to use\n")
        return name

    def getExcludeServers(self, options, info, err_msg=""):
        """ Display menu for choosing a server type """
        LOG.debug("Getting exclude servers for {0}".format(info))
        self._outputTitleLines("WORKFLOW ENGINE - {0}".format(info), err_msg)
        print "\nEnter servers to exclude as a comma separated list"
        # if we are using the menu then we cannot be using --list
        if options.servertype == constants.ALL:
            choice = raw_input("\nOr hit return to run on all servers: \n")
        else:
            choice = raw_input("\nOr hit return to run on all {0} servers: \n"\
                                   .format(options.servertype))
        if choice == "":
            servers = None
        else:
            servers = choice
        return servers

    def getMenuSingleTask(self, err_msg=""):
        """ Display menu for choosing a single task and server"""
        LOG.debug("Getting task id")
        self._outputTitleLines("WORKFLOW ENGINE - Select task", err_msg)
        task = raw_input("\nEnter id of task to use\n")
        return task

    def getMenuSingleTaskServers(self, options, err_msg=""):
        """ Displays sub-menu to determine whether to run task on
            all servers, or single server"""
        self._outputTitleLines("WORKFLOW ENGINE - {0}".format(options.task),
                               err_msg)
        # if we are using the menu then we cannot be using --list
        print " [1] Run {0} on all servers".format(options.task)
        print " [2] Run {0} on single server".format(options.task)
        LOG.debug("Requesting further details for {0} task".\
                                                  format(options.task))
        choice = raw_input("\nPlease select your option or q to quit:\n")
        if choice == "q":
            return False
        if not utils.digit_in_range(choice, 2):
            return self.getMenuSingleTaskServers(options, \
                          "Invalid option {0}".format(choice))
        val = int(choice)
        if val == 1:
            if options.exclude == None:
                options.exclude = self.getExcludeServers(options, options.task)
            options.servername = constants.ALL
            return True
        elif val == 2:
            options.servername = self.getMenuSingleServer(options.task)
        return True

    def getEditMenu(self, options, err_msg=""):
        """ Displays sub-menu to determine what options to edit """
        self._outputTitleLines("WORKFLOW ENGINE - Edit options", err_msg)
        print " [1] Configure information tag for phase"
        print " [2] Configure error tag for phase"
        print " [3] Configure arguments in display status information line"
        print "[4] Configure set variable tag"
        print "[5] Configure timeout"
        print "[6] Configure output level"
        choice = raw_input("\nPlease select your option or q to quit:\n")
        if choice == "q":
            return False
        if not utils.digit_in_range(choice, 6):
            return self.getEditMenu(options,
                                "Invalid option {0}".format(choice))
        val = int(choice)
        if val == 1:
            return self.getEditPhaseName(True)
        elif val == 2:
            return self.getEditPhaseName(False)
        elif val == 3:
            return self.getEditArguments()
        elif val == 4:
            return self.setParameter("set variable", wfconfig.SETVAR)
        elif val == 5:
            return self.setTimeout(options)
        elif val == 6:
            return self.setOutputLevel(options)

    def getEditPhaseName(self, is_info, err_msg=""):
        """ Asks user which phase want to change info or error tag for
            Arguments:
                is_info: True if changing info tag, False if error
                err_msg: Whether error message to display
            Returns:
                True if set parameter, else False
        """
        if is_info:
            tagname = "information"
            paramname = "_INFO"
        else:
            tagname = "error"
            paramname = "_ERR"
        self._outputTitleLines("WORKFLOW ENGINE - Edit {0} tags".\
                          format(tagname), err_msg)
        print " [1] Configure display {0} tag".format(tagname)
        print " [2] Configure precheck {0} tag".format(tagname)
        print " [3] Configure execute {0} tag".format(tagname)
        print " [4] Configure postcheck {0} tag".format(tagname)
        choice = raw_input("\nPlease select your option or q to quit:\n")
        if choice == "q":
            return False
        if not utils.digit_in_range(choice, 4):
            return self.getEditPhaseName("Invalid option {0}".format(choice))
        val = int(choice)
        if val == 1:
            phase = "DISPLAY"
        elif val == 2:
            phase = "PRECHECK"
        elif val == 3:
            phase = "EXECUTE"
        else:
            phase = "POSTCHECK"

        return self.setParameter("{0} {1} tag".format(phase, tagname),
                         phase + paramname)

    def setParameter(self, description, cfgparam):
        """ Asks and sets parameter in the wfconfig dictionary
            Arguments:
                description: text to display when asking for param value
                cfgparam: name of parameter in wfconfig dict to set
            Returns:
                True if set parameter
                False if user didn't want to set parameter
        """
        choice = raw_input(
                  "\nEnter value for {0} parameter, or return to quit:\n".\
                                           format(description))
        if len(choice) == 0:
            return False
        LOG.debug("Setting {0} to {1}".format(cfgparam, choice))
        self.config.cfg[cfgparam] = choice
        return True

    def getEditArguments(self, err_msg=""):
        """ Displays the user the choice of display information tags
            can set """
        self._outputTitleLines("WORKFLOW ENGINE - Edit status arguments",
                               err_msg)
        print " [1] Configure software version tag"
        print " [2] Configure server type tag"
        print " [3] Configure os version tag"
        choice = raw_input("\nPlease select your option or q to quit\n")
        if choice == "q":
            return False
        if not utils.digit_in_range(choice, 3):
            return self.getEditArguments("Invalid option {0}".format(choice))
        val = int(choice)
        if val == 1:
            return self.setParameter("software version", wfconfig.SWVER)
        elif val == 2:
            return self.setParameter("server type", wfconfig.TYPE)
        elif val == 3:
            return self.setParameter("os version", wfconfig.OSVER)

    def setTimeout(self, options, err_msg=""):
        """ Displays the menu to get the timeout value"""
        self._outputTitleLines("WORKFLOW ENGINE - Edit timeout", err_msg)
        choice = raw_input("\nPlease enter timeout (secs) or q to quit\n")
        if choice == "q":
            return False
        if not utils.digit_in_range(choice, sys.maxint):
            return self.setTimeout(options,
                                   "Invalid value {0}".format(choice))
        val = int(choice)
        options.timeout = val
        return True

    def _outputTitleLines(self, line, err_msg):
        """ Clears page and outputs line in center with hyphens underneath"""
        os.system('clear')
        print line.center(self.term_size)
        print HYPHEN_LINE[:len(line)].center(self.term_size)
        print err_msg
        print ""

    def _digitInRange(self, choice, max_val, min_val=1):
        """ Verifies choice is integer in range 1->max """
        if not choice.isdigit():
            return False
        else:
            val = int(choice)
            if val < min_val or val > max_val:
                return False
        return True

    def getMenuTag(self, options, err_msg=""):
        """ Displays sub-menu to get tag to run
            Returns:
                True if entered tag
                False if want to quit"""
        self._outputTitleLines("WORKFLOW ENGINE - Select tag",
                               err_msg)
        # if we are using the menu then we cannot be using --list
        tag = raw_input("\nEnter tag to run or enter to quit\n")
        if len(tag) == 0:
            return False
        else:
            options.tag = tag
            options.phase = constants.OPT_EXECUTE
            return self.getMenuServers(options,
                                    "{0} tag".format(options.tag),
                                    err_msg)

    def setOutputLevel(self, options, err_msg=""):
        """ Displays the menu to get the output level"""
        self._outputTitleLines("WORKFLOW ENGINE - Set output level", err_msg)
        print " [0] Quiet (suppress info and error tags)"
        print " [1] Output error tags only"
        print " [2] Output info and error tags"
        choice = raw_input("\nPlease select your option or q to quit\n")
        if choice == "q":
            return False
        if not utils.digit_in_range(choice, 2, 0):
            return self.setOutputLevel(options, "Invalid option {0}".\
                                               format(choice))
        val = int(choice)
        options.output_level = val
        return True

"""Responsible for getting user input about whether to run tasks
   and user input about whether to go ahead with manual reset
   @copyright: Ammeon Ltd

"""
import logging
import os
from wfeng import constants
from wfeng import wfconfig
import sys
import utils
import errno

SKIP_PROMPT = "Do you wish to run task (y), skip (s) or exit (n)?:\n"
SKIP_SERVER_PROMPT = "Do you wish to skip all tasks on server {0}(y/n)?:\n"
HOST_PROMPT = "Please enter {0} version of host {1}: \n"
HYPHEN_LINE = "---------------------------------------------------------------"
RESET_PROMPT1 = "There are completed tasks dependent on task {0}"
RESET_PROMPT2 = "Do you want to force reset on task {0}(y/n)?:\n"


LOG = logging.getLogger(__name__)


class InputMgr(object):
    """Performs requests to get info from user as to whether to run
       commands"""

    def askRunSkipTask(self, task, excluded):
        """Prompts user whether to run, skip task.

           Args:
               task: StatusTask to run
               excluded: Current list of servers to exclude, is updated
               if user chooses to skip all tasks on this server
           Returns:
               int: 0 to run, 1 to skip, 2 to exit
        """
        ret_val = 0
        choice = ""
        try:
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
        except EOFError:
            # Input stream has ended unexpectedly, assume user done Ctrl-C
            ret_val = 2
        except IOError as e:
            if e.errno != errno.EINTR:
                # IOError is not an interrupt - so not Ctrl-C
                raise
            else:
                ret_val = 2
        return ret_val

    def askContinue(self, wfstatus):
        """Asks user whether to continue or not, details of question to ask
           are in wfstatus object.

           Args:
               wfstatus:  WorkflowStatus object with details of question
           Returns:
               boolean: True if should continue, False otherwise
        """
        run = True
        val = None
        try:
            while not wfstatus.isValidResponse(val):
                val = raw_input(wfstatus.user_msg)
                if wfstatus.isStopResponse(val):
                    run = False
        except EOFError:
            # Input stream has ended unexpectedly, assume user done Ctrl-C
            run = False
        except IOError as e:
            if e.errno != errno.EINTR:
                # IOError is not an interrupt - so not Ctrl-C
                raise
            else:
                run = False
        return run

    def getVersion(self, htype, host):
        """ Asks user what version host is at

            Args:
                host:  Name of host to get version from
                htype: Type of version, software or OS
            Returns:
                Version entered
        """
        val = None
        while val == None:
            val = raw_input(HOST_PROMPT.format(htype, host))
        return val


class DynamicMenuMgr(object):
    """ Class that provides interactive menu driven processing for dynamic
        escape and dynamic pause """

    def __init__(self, term_size, config, hosts, validator):
        self.term_size = term_size
        self.config = config
        self.hosts = hosts
        self.validator = validator

    def getDynamicAlteration(self, wfsys, msgs):
        """ interactively obtains the details for the dynamic pause/esc
            alteration

            Args:
                wfsys: the workflow
                msgs: list to hold messages to be displayed to user
            Returns:
                dictionary containing the alteration details - empty if
                errors encountered, None if quitting
        """
        if not len(msgs) == 0:
            LOG.info("\n\n\n")
            for m in msgs:
                LOG.info(m)
            choice = raw_input(
                  "\nPress enter to continue\n")
            msgs = []

        utils.outputTitleLines("WORKFLOW ENGINE DYNAMIC ALTERATIONS", "",
                               self.term_size, HYPHEN_LINE)

        print " [1] Enter new dynamic ESCAPE task"
        print " [2] Enter new dynamic PAUSE task"
        print " [3] Delete existing dynamic ESCAPE task"
        print " [4] Delete existing dynamic PAUSE task"
        choice = raw_input(
            "\nPlease select your option or q to quit:\n")

        if choice == "q":
            return None
        if not utils.digit_in_range(choice, 4):
            msgs.append("Invalid option {0}".format(choice))
            return {}

        val = int(choice)
        dtask = {}

        if val == 1:
            return self.getDynamicAddition(dtask, constants.DYNAMIC_ESCAPE,
                                           wfsys)
        elif val == 2:
            return self.getDynamicAddition(dtask, constants.DYNAMIC_PAUSE,
                                           wfsys)
        elif val == 3:
            return self.getDynamicRemoval(dtask, constants.DYNAMIC_ESCAPE,
                                           wfsys)
        elif val == 4:
            return self.getDynamicRemoval(dtask, constants.DYNAMIC_PAUSE,
                                           wfsys)
        else:
            LOG.debug("Option out of range - this should never happen as "
                      "should be protected by range test")
            return {}

    def getDynamicAddition(self, resDict, dyntype, wfsys):
        """ interactively obtains the details for the dynamic pause/esc
            addition

            Args:
                resdict: a dictionary to hold the addition details
                dyntype: specifies whether this is a pause or an escape
                wfsys: workflow sys object used in validation
            Returns:
                dictionary containing the alteration details - empty if
                errors encountered or if quitting
        """
        utils.outputTitleLines(
           "WORKFLOW ENGINE DYNAMIC ALTERATIONS - add %s task" % dyntype,
           "Enter task details, or type q into any field to quit back to menu",
                self.term_size, HYPHEN_LINE)
        resDict[constants.DYN_ACTION] = constants.DYNAMIC_ADD
        resDict[constants.DYN_TYPE] = dyntype
        while True:

            if not self.dynAddField(resDict, constants.DYN_ID,
                   "Enter %s task id" % dyntype, dyntype, wfsys):
                return {}

            if not self.dynAddField(resDict, constants.DYN_REFID,
                   "Enter reference id (task before/after which new "
                    "task will appear)", dyntype, wfsys):
                return {}

            if not self.dynAddField(resDict, constants.DYN_POS,
                   "Enter [before] to insert before ref task, or "
                     "[after] to insert after", dyntype, wfsys):
                return {}

            if not self.dynAddField(resDict, constants.DYN_MSG,
                   "msg", dyntype, wfsys):
                return {}

            if not self.dynAddHostAndServer(resDict, dyntype, wfsys):
                return {}

            if not self.dynAddField(resDict, constants.DYN_DEP,
                   "dependency", dyntype, wfsys):
                return {}

            if not self.dynAddField(resDict, constants.DYN_DEPSINGLE,
                   "depsingle", dyntype, wfsys):
                return {}

            if not self.dynAddField(resDict, constants.DYN_SWVER,
                   "swversion", dyntype, wfsys):
                return {}

            if not self.dynAddField(resDict, constants.DYN_OSVER,
                   "osversion", dyntype, wfsys):
                return {}

            if not self.dynAddField(resDict, constants.DYN_CHECKPARAMS,
                   "checkparams", dyntype, wfsys):
                return {}

            LOG.info(self.getDetails(resDict, dyntype))

            choice = ""
            while not choice == "q" and not choice == "y" and \
                       not choice == "a":
                choice = raw_input(
                  "\nPlease select y to insert %s task, a to amend entries, "
                     "or q to quit back to the main menu without inserting "
                     "the task:\n" % \
                       dyntype)
                if choice == "q":
                    LOG.debug("Quitting back to menu")
                    return {}
                if choice == "y":
                    LOG.debug("Dynamic addition ready for action")
                    return resDict
                if choice == "a":
                    LOG.debug("Amending dynamic addition entries")

    def getDynamicRemoval(self, resDict, dyntype, wfsys):
        """ interactively obtains the details for the dynamic pause/esc removal

            Args:
                resdict: a dictionary to hold the addition details
                dyntype: specifies whether this is a pause or an escape
                wfsys: workflow sys object used in validation
            Returns:
                dictionary containing the alteration details - empty if errors
                encountered or if quitting
        """
        utils.outputTitleLines(
           "WORKFLOW ENGINE DYNAMIC ALTERATIONS - remove %s task" % dyntype,
           "Enter task details, or type q into any field to quit back to menu",
             self.term_size, HYPHEN_LINE)
        resDict[constants.DYN_ACTION] = constants.DYNAMIC_REMOVE
        resDict[constants.DYN_TYPE] = dyntype

        while True:
            if not self.acceptExistingEntry(resDict, constants.DYN_ID):
                entryOK = False
                while not entryOK:
                    entryOK = True
                    localMsgs = []
                    if not self.getRawInput(resDict, constants.DYN_ID,
                           "Enter %s task id" % dyntype, None):
                        return {}
                    LOG.debug("Field %s entered as %s" % \
                               (constants.DYN_ID, resDict[constants.DYN_ID]))
                    if not self.validator.validExecuteTaskId(\
                                resDict[constants.DYN_ID], dyntype,
                                                    wfsys, localMsgs):
                        self.displayErrors(localMsgs)
                        entryOK = False
                    elif self.validator.hasDependents(\
                                   resDict[constants.DYN_ID], wfsys,
                                     localMsgs):
                        self.displayErrors(localMsgs)
                        entryOK = False
            choice = ""
            while not choice == "q" and not choice == "y" and \
                                                 not choice == "a":
                choice = raw_input(
                   "\nPlease select y to remove %s task, a to amend entry, "
                       "or q to quit back to the main menu without removing "
                     "the task:\n" % \
                       dyntype)
                if choice == "q":
                    LOG.debug("Quitting back to menu")
                    return {}
                if choice == "y":
                    LOG.debug("Dynamic removal ready for action")
                    return resDict

    def getRawInput(self, resDict, key, inputprompt, defaulter):
        promptStr = "\n%s: " % inputprompt
        choice = raw_input(promptStr).rstrip()
        if choice == "q":
            return False
        else:
            if choice == "":
                resDict[key] = defaulter
            else:
                resDict[key] = choice

        return True

    def acceptExistingEntry(self, resDict, entryKey):
        """ allows us to accept existing entry on an edit

        Args:
            resDict: the dictionary containing entries so far
            entryKey: the key of the existing entry to offer
        Returns:
            boolean: True if user accepts the entry
            False if the user rejects the entry
            False if there is no existing entry
        """
        try:
            val = resDict[entryKey]
        except KeyError:
            return False
        cont = True
        retval = True
        while cont:
            promptStr = "\nExisting [%s] entry: [%s]  Accept? y/n: " % \
                               (entryKey, val)
            choice = raw_input(promptStr)
            if choice.lower() == "y":
                cont = False
            elif choice.lower() == "n":
                cont = False
                retval = False
        return retval

    def dynAddHostAndServer(self, resDict, dyntype, wfsys):
        """handles input of host and server, for which values are co-dependent

           Args:
               resDict: the dictionary of entered fields being built
               dyntype: type of msgTask (pause or escape)
               wfsys: the current workflow - used in validation
           Returns:
               True if field value entered, or empty dict if getRawInput
               returned False (which indicates that a quit (q) was entered)
        """
        entriesOK = False
        while not entriesOK:
            entriesOK = True
            localMsgs = []
            LOG.info("\nEnter hosts and server types fields:")
            if not self.dynAddField(resDict, constants.DYN_HOSTS,
                                           "hosts", dyntype, wfsys):
                return {}

            if not self.dynAddField(resDict, constants.DYN_SERVER,
                                           "server", dyntype, wfsys):
                return {}

            if not self.validator.validHostsServer(\
                   resDict[constants.DYN_HOSTS], resDict[constants.DYN_SERVER],
                   resDict[constants.DYN_REFID], wfsys, self.hosts, localMsgs):
                self.displayErrors(localMsgs)
                entriesOK = False

        return True

    def dynAddField(self, resDict, fieldKey, fieldPrompt, dyntype, wfsys):
        """handles input of a single field, offering edit of existing value
           if present
           Note that for hosts and server the validation here is only for
           free text - further validation is applied in dynAddHostAndServer

           Args:
               resDict: the dictionary of entered fields being built
               fieldKey: the key of the current entry
               fieldPrompt: the prompt for this field
               dyntype: type of msgTask (pause or escape)
               wfsys: the current workflow - used in validation
           Returns:
               boolean: True if field value entered, False if getRawInput
                     returned False
                     (which indicates that a quit (q) was entered), or
                     the field was unrecognise (which should never happen)
        """
        if not self.acceptExistingEntry(resDict, fieldKey):
            entryOK = False
            while not entryOK:
                entryOK = True
                localMsgs = []
                if not self.getRawInput(resDict, fieldKey,
                           fieldPrompt, None):
                    return False
                LOG.debug("Field %s entered as %s" % \
                               (fieldKey, resDict[fieldKey]))
                if fieldKey == constants.DYN_ID:
                    if not self.validator.validUniqueTaskId(\
                                resDict[fieldKey], wfsys, localMsgs):
                        self.displayErrors(localMsgs)
                        entryOK = False
                elif fieldKey == constants.DYN_REFID:
                    if not self.validator.validRefId(\
                                  resDict[constants.DYN_REFID],
                                  wfsys, localMsgs):
                        self.displayErrors(localMsgs)
                        entryOK = False
                elif fieldKey == constants.DYN_POS:
                    if resDict[constants.DYN_POS] is not None:
                        if resDict[constants.DYN_POS].lower() == "before":
                            resDict[constants.DYN_POS] = \
                                             constants.DYNAMIC_BEFORE
                        elif resDict[constants.DYN_POS].lower() == "after":
                            resDict[constants.DYN_POS] = \
                                             constants.DYNAMIC_AFTER
                        else:
                            resDict[constants.DYN_POS] == None
                    if not self.validator.validPosition(\
                                  resDict[constants.DYN_POS],
                                  localMsgs):
                        self.displayErrors(localMsgs)
                        entryOK = False
                elif fieldKey == constants.DYN_MSG:
                    if not self.validator.validFreeTextLine(\
                                         resDict[constants.DYN_MSG],
                                         constants.FIELD_REQUIRED, localMsgs):
                        self.displayErrors(localMsgs)
                        entryOK = False
                    if not self.validator.validIniParam(\
                                 resDict[constants.DYN_MSG], wfsys, localMsgs):
                        self.displayErrors(localMsgs)
                        entryOK = False
                elif fieldKey == constants.DYN_HOSTS:
                    if not self.validator.validFreeTextLine(\
                            resDict[fieldKey],
                            constants.FIELD_REQUIRED, localMsgs):
                        self.displayErrors(localMsgs)
                        entryOK = False
                    if not self.validator.validHostsFormat(\
                             resDict[constants.DYN_HOSTS], localMsgs):
                        self.displayErrors(localMsgs)
                        entryOK = False
                elif fieldKey == constants.DYN_SERVER:
                    if not self.validator.validFreeTextLine(\
                            resDict[fieldKey],
                            constants.FIELD_REQUIRED, localMsgs):
                        self.displayErrors(localMsgs)
                        entryOK = False
                elif fieldKey == constants.DYN_DEP:
                    if not self.validator.validDependencies(\
                                    resDict[constants.DYN_DEP], wfsys,
                                    resDict[constants.DYN_REFID],
                                    resDict[constants.DYN_POS], localMsgs):
                        self.displayErrors(localMsgs)
                        entryOK = False
                elif fieldKey == constants.DYN_DEPSINGLE:
                    if not self.validator.validBooleanField(\
                                          resDict[constants.DYN_DEPSINGLE],
                                          constants.FIELD_OPTIONAL, localMsgs):
                        self.displayErrors(localMsgs)
                        entryOK = False
                    if not self.validator.validGroupDepSingle(\
                                   resDict[constants.DYN_DEPSINGLE],
                                   resDict[constants.DYN_REFID],
                                   resDict[constants.DYN_DEP], wfsys,
                                   localMsgs):
                        self.displayErrors(localMsgs)
                        entryOK = False
                elif fieldKey == constants.DYN_SWVER or \
                     fieldKey == constants.DYN_OSVER:
                    if not self.validator.validFreeTextLine(\
                                resDict[fieldKey],
                                constants.FIELD_OPTIONAL, localMsgs):
                        self.displayErrors(localMsgs)
                        entryOK = False
                    if not self.validator.validIniParam(\
                                    resDict[fieldKey], wfsys,
                                    localMsgs):
                        self.displayErrors(localMsgs)
                        entryOK = False
                elif fieldKey == constants.DYN_CHECKPARAMS:
                    if not self.validator.validCheckparams(\
                                        resDict[constants.DYN_CHECKPARAMS],
                                        localMsgs):
                        self.displayErrors(localMsgs)
                        entryOK = False
                    if not self.validator.validIniParam(\
                                    resDict[constants.DYN_CHECKPARAMS], wfsys,
                                    localMsgs):
                        self.displayErrors(localMsgs)
                        entryOK = False
                else:
                        LOG.info("Error: unrecognised field [%s]" % \
                                          fieldKey)
                        return False
        return True

    def displayErrors(self, msgs):
        """ displays errors from msgs list

            Args:
                msgs: list of errors
            Returns:
                n/a
        """
        if len(msgs) == 0:
            pass
        else:
            LOG.info("Error:")
            for m in msgs:
                LOG.info(m)

    def getDetails(self, resDict, dyntype):
        """ formats the new msgTask details as a string for display to user

            Args:
                reDict: dictionary of the msgTask details entered
                dyntype: which kind of dynamic task this is (pause or escape)
            Returns:
                string representation of the details
                or None if resDict is None
        """
        if resDict is None:
            return None
        return "%s: New task will be inserted %s existing task %s\n" \
                     "%s:[%s] %s:[%s] %s:[%s] %s:[%s] " \
                     "%s:[%s] %s:[%s] %s:[%s] %s:[%s] %s:[%s]" % \
                 (dyntype,
                  resDict[constants.DYN_POS],
                  resDict[constants.DYN_REFID],
                  constants.DYN_ID, resDict[constants.DYN_ID],
                  constants.DYN_MSG, resDict[constants.DYN_MSG],
                  constants.DYN_HOSTS, resDict[constants.DYN_HOSTS],
                  constants.DYN_SERVER, resDict[constants.DYN_SERVER],
                  constants.DYN_DEP, resDict[constants.DYN_DEP],
                  constants.DYN_DEPSINGLE, resDict[constants.DYN_DEPSINGLE],
                  constants.DYN_SWVER, resDict[constants.DYN_SWVER],
                  constants.DYN_OSVER, resDict[constants.DYN_OSVER],
                  constants.DYN_CHECKPARAMS,
                  resDict[constants.DYN_CHECKPARAMS])


class MenuMgr(object):
    """ Class that provides command line menu and gets input """

    def __init__(self, term_size, config):
        self.term_size = term_size
        self.config = config

    def getOptions(self, options, err_msg=""):
        """ Get menu options, and populate options object

            Args:
                options: WorkflowOptions
                err_msg: error message to display
            Returns:
                boolean: True if ok, False if should quit
        """
        utils.outputTitleLines("WORKFLOW ENGINE", err_msg,
                               self.term_size, HYPHEN_LINE)
        # if we are using the menu then we cannot be using --list
        print " [1] Run display deployment"
        print " [2] Run pre-checks"
        print " [3] Run execute workflow"
        print " [4] Run post-checks"
        print " [5] Run named tasks"
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
            options.unparsed_task = self.getMenuTaskList()
            if options.unparsed_task != None:
                options.task = utils.split_commas(options.unparsed_task)
            options.phase = constants.OPT_POSTCHECK
            return self.getMenuTaskListServers(options,
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
            all servers, servers of particular type, selected server names"""
        return self.getMenuServers(options,
                                    "{0} phase".format(options.phase),
                                    err_msg)

    def getMenuServers(self, options, desc, err_msg=""):
        """ Displays sub-menu to determine whether to run on
            all servers, servers of particular type, selected servernames.
            Used when running phase or tagged set"""
        utils.outputTitleLines("WORKFLOW ENGINE - {0}".format(desc),
                               err_msg, self.term_size, HYPHEN_LINE)
        # if we are using the menu then we cannot be using --list
        print " [1] Run {0} on all servers".format(desc)

        print " [2] Run {0} on all servers of selected types".format(desc)

        print " [3] Run {0} on selected servers".format(desc)
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
            options.unparsed_servertypes = constants.ALL
            options.unparsed_servernames = constants.ALL
        elif val == 2:
            options.unparsed_servernames = constants.ALL
            options.unparsed_servertypes = self.getMenuServerTypes(options)
        elif val == 3:
            options.unparsed_servernames = self.getMenuSelectedServers(desc)
            options.unparsed_servertypes = constants.ALL
        if val == 1 or val == 2:
            # Check if want to exclude server
            if options.exclude == None:
                options.exclude = self.getExcludeServers(options,
                                                         desc)
        return True

    def getMenuServerTypes(self, options, err_msg=""):
        """ Display menu for choosing a server type """
        LOG.debug("Getting server type for phase {0}".format(options.phase))
        utils.outputTitleLines("WORKFLOW ENGINE - {0}".format(options.phase),
                  err_msg, self.term_size, HYPHEN_LINE)
        # TODO: Improve by showing them the choice of server types
        # in the workflow
        choice = raw_input(
              "\nEnter comma-separated list of server types to use\n")
        return choice

    def getMenuSelectedServers(self, info, err_msg=""):
        """ Display menu for choosing servernames"""
        LOG.debug("Getting server name for {0}".format(info))
        utils.outputTitleLines("WORKFLOW ENGINE - {0}".format(info),
                         err_msg, self.term_size, HYPHEN_LINE)
        name = raw_input(
               "\nEnter comma-separated list of server names to use\n")
        return name

    def getExcludeServers(self, options, info, err_msg=""):
        """ Display menu for choosing excluded servers """
        LOG.debug("Getting exclude servers for {0}".format(info))
        utils.outputTitleLines("WORKFLOW ENGINE - {0}".format(info),
                              err_msg, self.term_size, HYPHEN_LINE)
        print "\nEnter servers to exclude as a comma separated list"
        # if we are using the menu then we cannot be using --list
        if options.unparsed_servertypes == constants.ALL:
            choice = raw_input("\nOr hit return to run on all servers: \n")
        else:
            choice = raw_input("\nOr hit return to run on all {0} servers: \n"\
                                   .format(options.unparsed_servertypes))
        if choice == "":
            servers = None
        else:
            servers = choice
        return servers

    def getMenuTaskList(self, err_msg=""):
        """ Display menu for choosing a task list and server"""
        LOG.debug("Getting task id/s")
        utils.outputTitleLines("WORKFLOW ENGINE - Select tasks", err_msg,
                               self.term_size, HYPHEN_LINE)
        task = \
            raw_input("\nEnter comma-separated list of the task ids to use\n")
        return task

    def getMenuTaskListServers(self, options, err_msg=""):
        """ Displays sub-menu to determine whether to run tasks on
            all servers, or selected servers"""
        utils.outputTitleLines("WORKFLOW ENGINE - {0}".format(options.task),
                               err_msg, self.term_size, HYPHEN_LINE)
        # if we are using the menu then we cannot be using --list
        print " [1] Run {0} on all servers".format(options.task)
        print " [2] Run {0} on selected servers".format(options.unparsed_task)
        LOG.debug("Requesting further details for {0} task".\
                                                format(options.unparsed_task))
        choice = raw_input("\nPlease select your option or q to quit:\n")
        if choice == "q":
            return False
        if not utils.digit_in_range(choice, 2):
            return self.getMenuTaskListServers(options, \
                          "Invalid option {0}".format(choice))
        val = int(choice)
        if val == 1:
            if options.exclude == None:
                options.exclude = self.getExcludeServers(options, options.task)
            options.unparsed_servernames = constants.ALL
            return True
        elif val == 2:
            options.unparsed_servernames = \
                             self.getMenuSelectedServers(options.task)
        return True

    def getEditMenu(self, options, err_msg=""):
        """ Displays sub-menu to determine what options to edit """
        utils.outputTitleLines("WORKFLOW ENGINE - Edit options", err_msg,
                               self.term_size, HYPHEN_LINE)
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

            Args:
                is_info: True if changing info tag, False if error
                err_msg: Whether error message to display
            Returns:
                boolean: True if set parameter, else False
        """
        if is_info:
            tagname = "information"
            paramname = "_INFO"
        else:
            tagname = "error"
            paramname = "_ERR"
        utils.outputTitleLines("WORKFLOW ENGINE - Edit {0} tags".\
                          format(tagname), err_msg, self.term_size,
                          HYPHEN_LINE)
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

            Args:
                description: text to display when asking for param value
                cfgparam: name of parameter in wfconfig dict to set
            Returns:
                boolean: True if set parameter
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
        utils.outputTitleLines("WORKFLOW ENGINE - Edit status arguments",
                               err_msg, self.term_size, HYPHEN_LINE)
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
        utils.outputTitleLines("WORKFLOW ENGINE - Edit timeout", err_msg,
                               self.term_size, HYPHEN_LINE)
        choice = raw_input("\nPlease enter timeout (secs) or q to quit\n")
        if choice == "q":
            return False
        if not utils.digit_in_range(choice, sys.maxint):
            return self.setTimeout(options,
                                   "Invalid value {0}".format(choice))
        val = int(choice)
        options.timeout = val
        return True

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

            Args:
                options: options chosen
                err_msg: current error message to display
            Returns:
                boolean: True if entered tag, False if want to quit
        """
        utils.outputTitleLines("WORKFLOW ENGINE - Select tag",
                               err_msg, self.term_size, HYPHEN_LINE)
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
        utils.outputTitleLines("WORKFLOW ENGINE - Set output level",
                           err_msg, self.term_size, HYPHEN_LINE)
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

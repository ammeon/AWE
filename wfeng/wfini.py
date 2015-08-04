""" Reads in ini file and sets environment
@copyright: Ammeon Ltd
"""
import os
import logging
from wfeng import constants

log = logging.getLogger(__name__)
INI_ERROR = "Failed to load {0} ini file - expecting parameter definition "\
            "(param=values) but found: {1}"
INI_WORD_ERR = "Failed to load {0} ini file - parameter name must be a " \
               "single word but was {1}: {2}"


class WfengIni(object):
    """ Represents class that reads ini files"""

    def __init__(self):
        self.vars = {}

    def load(self, filename=constants.INI_FILE):
        """ Updates vars with values from ini file filename.
            A parameter value without enclosing double-quotes must be single
            line
            A parameter value with enclosing double-quotes may be single or
            multiple lines
            A multi-line value is one which starts with a double quote at the
            beginning of the value part, and is terminated by double quote at
            the end of a line
            Enclosing double-quotes, if present, are removed from the variable
            string
            Returns:
                boolean: indicating if loaded ok or not
        """
        if os.path.isfile(filename):
            continuation = False
            currVar = ""
            with open(filename) as cfgfile:
                for line in cfgfile:
                    # this must be the start point of a parameter definition
                    if not continuation:
                        # empty lines, or lines starting with #, when not
                        # within a multiline entry, are ignored
                        if not line.startswith("#") and not line.strip() == "":
                            name, sep, var = line.partition("=")
                            if not sep and not var:
                                # if sep and var are empty then the = sign
                                # was not found, and since we are expecting
                                # new param this is an error
                                log.error(INI_ERROR.format(filename,
                                                      line.strip()))
                                return False
                            namelen = len(name.strip().split())
                            if namelen != 1:
                                #name of the parameter must be a single word
                                log.error(INI_WORD_ERR.format(filename,
                                                     namelen, name.strip()))
                                return False
                            if name not in constants.INI_RESERVED_VARS:
                                varUnstripped = var
                                varStripped = var.strip()
                                quotestart = varStripped.startswith('"')
                                quoteend = varStripped.endswith('"')
                                if quotestart and not quoteend:
                                    # this is the start of a multiline value
                                    # remove initial quote and set continuation
                                    # flag
                                    continuation = True
                                    currVar = varUnstripped[1:]
                                elif quotestart and quoteend:
                                    # this is a single line value enclosed in
                                    # quotes, remove initial and terminal
                                    # quotes and unset continuation flag
                                    continuation = False
                                    currVar = varStripped[1:]
                                    currVar = currVar[:-1]
                                else:
                                    # we have no initial quotation mark, so
                                    # this cannot be a multiline param
                                    currVar = varStripped
                                    continuation = False

                                if not continuation:
                                    # if there are no subesquent lines expected
                                    # then update the parameter
                                    os.environ[name.strip()] = currVar.strip()
                                    self.vars[name.strip()] = currVar.strip()
                                    log.debug("parameter %s has value %s" % \
                                              (name.strip(), currVar.strip()))
                            else:
                                log.error("Failed to load {0} ini file - "\
                                    "parameter {1} is a reserved word".format(
                                         filename, line.strip()))
                                return False

                    # this must be the continuation of a multiline parameter
                    # value
                    else:
                        varUnstripped = line
                        # on continuation lines we want to strip ONLY the
                        # linefeed
                        varStripped = line.rstrip('\n')
                        quoteend = varStripped.endswith('"')
                        if quoteend:
                            # this is a terminating line, so remove terminal
                            # quote and unset continuation flag
                            currVar = currVar + varStripped[:-1]
                            continuation = False
                            # since there are no subesquent lines expected
                            # then update the parameter
                            os.environ[name.strip()] = currVar
                            self.vars[name.strip()] = currVar
                            log.debug("parameter %s has value %s" % \
                                      (name.strip(), currVar.strip()))
                        else:
                            currVar = currVar + varUnstripped

            # if at end of file we still have continuation flag set then
            # there is a problem
            if continuation:
                log.error("Failed to load " \
                          "{0} ini file - missing terminating quote".format(
                                           filename))
                return False

            log.debug("Successfully loaded {0} ini file".format(filename))
            return True
        else:
            log.error("Failed to locate ini file {0}".format(filename))
            return False

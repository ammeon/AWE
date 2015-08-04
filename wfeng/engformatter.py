"""Modules represents top level manager class
@copyright: Ammeon Ltd
"""
import logging
from wfeng import constants


class WfengFormatter(logging.Formatter):

    def __init__(self, fmt=None, datefmt=None):
        logging.Formatter.__init__(self, fmt, datefmt)

    def formatTime(self, record, datefmt=None):
        if record.levelno == constants.DEBUGNOTIME or \
           record.levelno == constants.INFONOTIME or \
           record.levelno == constants.ERRORNOTIME:
            return ""
        else:
            return logging.Formatter.formatTime(self, record, datefmt)

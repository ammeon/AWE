#!/bin/sh
BASEDIR=`dirname $0`
. "${BASEDIR}/install_common_functions.lib"

UNKNOWN="unknown"
SUNOS="SunOs"
LINUX="Linux"
OPSYS=${UNKNOWN}


# ********************************************************************
#
#       Configuration Section
#
# ********************************************************************



# ********************************************************************
#
#       Pre-execution Operations
#
# ********************************************************************



# ********************************************************************
#
# 	functions
#
# ********************************************************************
read_defs()
{
   # work out whether we are on SunOS or Linux
   uname -s > /dev/null 2>&1
   if [ $? -eq 0 ]
   then 
       uname -s | grep -i ${SUNOS} > /dev/null 2>&1
       if [ $? -eq 0 ]
       then
           OPSYS=${SUNOS}
           . "${BASEDIR}/solaris_def.lib"
       fi
   fi
   uname -o > /dev/null 2>&1
   if [ $? -eq 0 ]
   then 
       uname -s | grep -i ${LINUX}  > /dev/null 2>&1
       if [ $? -eq 0 ]
       then
           OPSYS=${LINUX}
           . "${BASEDIR}/generic_def.lib"
        fi
    fi
    echo "operating system: ${OPSYS}"

    # if unable to identify operating system then display message and exit with error
    if [ ${OPSYS} = ${UNKNOWN} ]
    then
        echo "system was not detected as either of Solaris or Linux"
        exit 1
    fi
}


# ********************************************************************
#
#       Main body of program
#
# ********************************************************************

STATUS=0
read_defs

if [ "${AWE_HOME}" = "" ]
then
    AWE_HOME=/opt/ammeon/wfeng
    $ECHO "Using default installation directory of ${AWE_HOME}"
else
    $ECHO "Using installation directory of ${AWE_HOME}"
fi

$ECHO "UnInstalling wfeng"
$ECHO
$ECHO
python setup.py uninstall
res=$?
if [ $res -ne 0 ] 
then
    $ECHO "Failed to uninstall wfeng from ${AWE_HOME}"
    STATUS=1
fi
$ECHO "Checking if any errors encountered during uninstallation of the wfeng before exiting"
if [ $STATUS -ne 0 ]
then
    $ECHO "Errors were encountered during uninstallation of the wfeng - check logging"
    exit 1
else
    $ECHO "Uninstall successful!"
fi

exit 0



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

copy_file()
{
    src_fle=$1
    dst_fle=$2
    local result=0
  
    $ECHO "Copying file $src_fle to ${dst_fle}"

    $CP $src_fle $dst_fle
    result=$?
    if [ $result -ne 0 ] 
    then
        $ECHO "Failed to copy file $src_fle to ${dst_fle}"
        STATUS=1
    else
        if [ "${AWE_USER}" != "" ]
        then
            $ECHO "Changing ownership of file ${dst_fle} to be ${AWE_USER}:${AWE_USER}"
            $CHOWN ${AWE_USER}:${AWE_USER} ${dst_fle}
            result=$?
            if [ $result -ne 0 ] 
            then
                $ECHO "Failed to change ownership of file ${dst_fle}"
                STATUS=1
            fi
        fi   
    fi

    return 0

}

backup_file() {
    src_file=$1
    dest_file=$2
    $ECHO "Checking if file ${src_file} exists"

    if [ -f ${src_file} ]
    then  
        $ECHO "Copying file ${src_file} to ${dest_file}"
        $CP $src_file $dest_file
        result=$?
        if [ $result -ne 0 ] 
        then
            $ECHO "Failed to backup file $src_file to ${dest_file}"
            STATUS=1
        else
            if [ "${AWE_USER}" != "" ]
            then
                $ECHO "Changing ownership of file ${dest_file} to be ${AWE_USER}:${AWE_USER}"
                $CHOWN ${AWE_USER}:${AWE_USER} ${dest_file}
                result=$?
                if [ $result -ne 0 ] 
                then
                    $ECHO "Failed to change ownership of file ${dest_file}"
                    STATUS=1
                fi
            fi   
        fi
    fi
    return 0
}

move_file() {
    src_file=$1
    dest_file=$2
    $ECHO "Checking if file ${src_file} exists"

    if [ -f ${src_file} ]
    then  
        $ECHO "Moving file ${src_file} to ${dest_file}"
        $MV $src_file $dest_file
        result=$?
        if [ $result -ne 0 ] 
        then
            $ECHO "Failed to move file $src_file to ${dest_file}"
            STATUS=1
        else
            if [ "${AWE_USER}" != "" ]
            then
                $ECHO "Changing ownership of file ${dest_file} to be ${AWE_USER}:${AWE_USER}"
                $CHOWN ${AWE_USER}:${AWE_USER} ${dest_file}
                result=$?
                if [ $result -ne 0 ] 
                then
                    $ECHO "Failed to change ownership of file ${dest_file}"
                    STATUS=1
                fi
            fi   
        fi
    fi
    return 0
}

copy_file_with_bkp()
{
    src_fle=$1
    dst_fle=$2
    local result=0

    $ECHO "Checking if file ${dst_fle} already exists"

    if [ -f ${dst_fle} ]
    then  
        $ECHO "Copying file $src_fle to ${dst_fle}.${VERSION}"

        $CP $src_fle $dst_fle.${VERSION}
        result=$?
    else
        $ECHO "Copying file $src_fle to ${dst_fle}"

        $CP $src_fle $dst_fle
        result=$?
    fi
        
    if [ $result -ne 0 ] 
    then
        $ECHO "Failed to copy file $src_fle to ${dst_fle}"
        STATUS=1
    else
        if [ "${AWE_USER}" != "" ]
        then
            $ECHO "Changing ownership of file ${dst_fle} to be ${AWE_USER}:${AWE_USER}"
            $CHOWN ${AWE_USER}:${AWE_USER} ${dst_fle}
            result=$?
            if [ $result -ne 0 ] 
            then
                $ECHO "Failed to change ownership of file ${dst_fle}"
                STATUS=1
            fi
        fi   
    fi

    return 0
    

}

# ********************************************************************
#
#       Main body of program
#
# ********************************************************************

STATUS=0
read_defs
VERSION=`$CAT RELEASE_INFO.txt | $CUT -d ' ' -f 1`

if [ "${AWE_HOME}" = "" ]
then
    AWE_HOME=/opt/ammeon/wfeng
    $ECHO "Using default installation directory of ${AWE_HOME}"
else
    $ECHO "Using installation directory of ${AWE_HOME}"
fi

$ECHO "Backup existing wfeng.cfg and wfeng.ini"
backup_file ${AWE_HOME}/cfg/wfeng.cfg ${AWE_HOME}/cfg/wfeng.cfg.pre_${VERSION}
backup_file ${AWE_HOME}/cfg/wfeng.ini ${AWE_HOME}/cfg/wfeng.ini.pre_${VERSION}

$ECHO "Installing wfeng"
$ECHO
$ECHO
python setup.py install --root=${AWE_HOME} --install-scripts=lib --install-lib=lib --install-data= --force
res=$?
if [ $res -ne 0 ] 
then
    $ECHO "Failed to install wfeng into ${AWE_HOME}"
    STATUS=1
else
    if [ "${AWE_USER}" != "" ]
    then
        $ECHO "Changing ownership of ${AWE_HOME} to be ${AWE_USER}:${AWE_USER}"
        $CHOWN -R ${AWE_USER}:${AWE_USER} ${AWE_HOME}
        res=$?
        if [ $res -ne 0 ] 
        then
            $ECHO "Failed to change ownership of directory ${AWE_HOME}"
            STATUS=1
        fi
    fi
fi

$ECHO "Backup new cfg and ini files"
backup_file ${AWE_HOME}/cfg/wfeng.cfg ${AWE_HOME}/cfg/wfeng.cfg.${VERSION}
backup_file ${AWE_HOME}/cfg/wfeng.ini ${AWE_HOME}/cfg/wfeng.ini.${VERSION}

$ECHO "Restore pre-upgrade cfg and ini files"
move_file ${AWE_HOME}/cfg/wfeng.cfg.pre_${VERSION} ${AWE_HOME}/cfg/wfeng.cfg
move_file ${AWE_HOME}/cfg/wfeng.ini.pre_${VERSION} ${AWE_HOME}/cfg/wfeng.ini

#  Check if the alias exists in the profile
if [ "${AWE_USER}" != "" ]
then
    USER_HOME=`$GREP "^${AWE_USER}:" /etc/passwd | $CUT -d ":" -f6`
else
    USER_HOME=`$GREP "^root:" /etc/passwd | $CUT -d ":" -f6`
fi
AWE_USER_PROFILE=`eval echo ${USER_HOME}/.profile`
if [  ! -f "${AWE_USER_PROFILE}" ]
then
    AWE_USER_PROFILE=`eval echo ${USER_HOME}/.bash_profile`
fi

if [ -f "${AWE_USER_PROFILE}" ]
then
    
    $ECHO "Checking if wfeng alias exists in the ${AWE_USER_PROFILE} login profile"
    ${GREP} "workfloweng.py" ${AWE_USER_PROFILE} | grep alias > /dev/null
    res=$?
    if [ $res -eq 0 ]
    then
        $ECHO "Removing old alias for wfeng"
        ${GREP} -v "workfloweng.py" ${AWE_USER_PROFILE} | ${GREP} -v "Setup alias for Workflow Engine" > ${AWE_USER_PROFILE}.tmp
        $ECHO "Removing old AWE_HOME"
        ${GREP} -v "AWE_HOME" ${AWE_USER_PROFILE}.tmp > ${AWE_USER_PROFILE}
    fi
    $ECHO "Adding alias wfeng='${AWE_HOME}/lib/workflowEng.py' to the ${AWE_USER_PROFILE} login profile"
    $ECHO "#Setup alias for Workflow Engine" >> ${AWE_USER_PROFILE}
    $ECHO "alias wfeng='${AWE_HOME}/lib/workfloweng.py'" >> ${AWE_USER_PROFILE}
    $ECHO "AWE_HOME=${AWE_HOME}" >> ${AWE_USER_PROFILE}
    $ECHO "export AWE_HOME" >> ${AWE_USER_PROFILE}
else
    $ECHO "To setup Workflow Engine, please add following command to your login profile"
    $ECHO "alias wfeng='${AWE_HOME}/lib/workfloweng.py'"
fi

#****************************
# Check STATUS value
#****************************

$ECHO "Checking if any errors encountered during installation of the wfeng before exiting"
if [ $STATUS -ne 0 ]
then
    $ECHO "Errors were encountered during installation of the wfeng - check logging"
    exit 1
else
    $ECHO "Install successful!"
fi

exit 0



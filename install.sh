#!/usr/bin/bash

BASEDIR=$(dirname $0)
source "${BASEDIR}/install_common_functions.lib"

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

copy_file_with_bkp()
{
    src_fle=$1
    dst_fle=$2
    local result=0

    $ECHO "Checking if file ${dst_fle} already exists"

    if [ -f ${dst_fle} ]
    then  
        $ECHO "Copying file $src_fle to $${dst_fle}.${VERSION}"

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

source "${BASEDIR}/solaris_def.lib"

STATUS=0

if [ "${AWE_HOME}" == "" ]
then
    AWE_HOME=/opt/ammeon/wfeng
    $ECHO "Using default installation directory of ${AWE_HOME}"
else
    $ECHO "Using installation directory of ${AWE_HOME}"
fi

for dir in lib xsd log etc .lock cfg license
do
    if [ ! -d ${AWE_HOME}/${dir} ]
    then
        $ECHO "Creating directory ${AWE_HOME}/${dir}"

        $MKDIR -p ${AWE_HOME}/${dir}
        res=$?
        if [ $res -eq 0 ]
        then
            if [ "${AWE_USER}" != "" ]
                then
                $ECHO "Changing ownership of directory ${AWE_HOME}/${dir} to be ${AWE_USER}:${AWE_USER}"
                $CHOWN ${AWE_USER}:${AWE_USER} ${AWE_HOME}/${dir}
                res=$?
                if [ $res -ne 0 ] 
                then
                    $ECHO "Failed to change ownership of directory ${AWE_HOME}/${dir}"
                    STATUS=1
                fi
            fi
        else
            $ECHO "Unable to create directory ${AWE_HOME}/${dir}"
            exit $res
        fi
    else
        $ECHO "Directory ${AWE_HOME}/${dir} exists"
    fi
done

$ECHO "Moving xsd files into ${AWE_HOME}/xsd/"
copy_file xsd/hosts.xsd ${AWE_HOME}/xsd/hosts.xsd
copy_file xsd/workflow.xsd ${AWE_HOME}/xsd/workflow.xsd

$ECHO "Moving cfg files into ${AWE_HOME}/cfg/"
copy_file_with_bkp cfg/wfeng.ini ${AWE_HOME}/cfg/wfeng.ini
copy_file_with_bkp cfg/wfeng.cfg ${AWE_HOME}/cfg/wfeng.cfg

$ECHO "Moving license files into ${AWE_HOME}/license/"
copy_file license/NOTICE.txt ${AWE_HOME}/license/NOTICE.txt
copy_file license/LICENSE.txt ${AWE_HOME}/license/LICENSE.txt

$ECHO "Moving RELEASE_INFO into ${AWE_HOME}"
copy_file RELEASE_INFO.txt ${AWE_HOME}/RELEASE_INFO.txt

curdir=`pwd`

cd ${AWE_HOME}/lib && $CP -R ${curdir}/wfeng .
res=$?
cd ${AWE_HOME}/lib && $CP ${curdir}/workfloweng.py .
res2=$?
if [ $res -ne 0 ]  || [ $res2 -ne 0 ]
then
    $ECHO "Failed to unpack AWE source into ${AWE_HOME}/lib"
    STATUS=1
else
    if [ "${AWE_USER}" != "" ]
    then
        $ECHO "Changing ownership of ${AWE_HOME}/lib/wfeng and ${AWE_HOME}/lib/workfloweng.py to be ${AWE_USER}:${AWE_USER}"
        $CHOWN -R ${AWE_USER}:${AWE_USER} ${AWE_HOME}/lib/workfloweng.py ${AWE_HOME}/lib/wfeng
        res=$?
        if [ $res -ne 0 ] 
        then
            $ECHO "Failed to change ownership of directory ${AWE_HOME}/lib/wfeng or file ${AWE_HOME}/lib/workfloweng.py"
            STATUS=1
        fi
    fi
fi

#  Check if the alias exists in the profile

AWE_USER_PROFILE=`eval echo ~${AWE_USER}/.profile`

if [ "${AWE_USER}" != "" ] && [ -f "${AWE_USER_PROFILE}" ]
then
    
    $ECHO "Checking if wfeng alias exists in the ${AWE_USER_PROFILE} login profile"
    ${GREP} "workfloweng.py" ${AWE_USER_PROFILE} > /dev/null
    res=$?
    if [ $res -eq 0 ]
    then
        $ECHO "alias wfeng='python ${AWE_HOME}/lib/workfloweng.py' already exists in ${AWE_USER_PROFILE}"
    else
        $ECHO "Adding alias wfeng='python ${AWE_HOME}/lib/workfloweng.py'to the ${AWE_USER_PROFILE} login profile"
        $ECHO "" >> ${AWE_USER_PROFILE}
        $ECHO "#Setup alias for Workflow Engine" >> ${AWE_USER_PROFILE}
        $ECHO "alias wfeng='python ${AWE_HOME}/lib/workfloweng.py'" >> ${AWE_USER_PROFILE}
    fi   
else

    $ECHO "To setup Workflow Engine, please add following command to your login profile"
    $ECHO "alias wfeng='python ${AWE_HOME}/lib/workfloweng.py'"
fi

#****************************
# Check STATUS value
#****************************

$ECHO "Checking if any errors encountered during installation of the wfeng before exiting"
if [ $STATUS -ne 0 ]
then
    $ECHO "Errors were encountered during installation of the wfeng - check logging"
    exit 1
fi

exit 0



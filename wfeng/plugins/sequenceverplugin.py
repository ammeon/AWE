""" Example version compare plugin
    @copyright: Ammeon Ltd
"""

""" Custom version plugins must implement a compare_version method as
    detailed below. This example uses sequence based numbering, e.g.
    1.2.3 compared to 2.1.1"""

def compare_version(version_req, current_version):
    """ Performs version comparison to report if host is already at required
        version

        Args:
            version_req: Version that want to be at
            current_version: Version that host is currently at
        Returns:
            True if current_version >= version_req
            False otherwise
        Raises:
            ValueError: if version is in unsupported format
    """
    if current_version == None:
        return False
    if version_req == None:
        return True
    if current_version == version_req:
        return True
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

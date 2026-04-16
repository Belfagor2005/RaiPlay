#!/bin/sh
pyv="$(python -V >&1)"
echo "$pyv"
echo "Checking Dependencies"
echo
if [ -d /etc/opkg ]; then
    echo "updating feeds"
    opkg update
    echo
    if [[ $pyv =~ "Python 3" ]]; then
        echo "checking python3-image"
        opkg install python3-image
        echo
        echo "checking python3-imaging"
        opkg install python3-imaging
        echo
        echo "checking python3-requests"
        opkg install python3-requests
        echo
        # echo "checking python3-multiprocessing"
        # opkg install python3-multiprocessing
        echo
    else
        echo "checking python-image"
        opkg install python-image
        echo
        echo "checking python-imaging"
        opkg install python-imaging
        echo
        echo "checking python-requests"
        opkg install python-requests
        echo
    fi
fi
exit 0
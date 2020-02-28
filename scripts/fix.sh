#!/bin/sh

if [ "$1" != "-f" ]; then
    # diff-index will return exit status 1 if there are uncommitted changes
    git update-index --refresh > /dev/null
    git diff-index --quiet HEAD --
fi

if [ $? -eq 0 ]; then
    set -ex
    isort -rc ptera/ tests/ examples/
    unimport -r ptera/ tests/ examples/
    black ptera/ tests/ examples/
else
    echo "ERROR: There are uncommitted changes. Commit changes, or use -f flag."
    exit 1
fi

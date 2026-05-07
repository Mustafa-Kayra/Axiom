#!/bin/bash


# clean up
rm -f dist/*

# build distribution
python3 -m build

# push to pypi
 python3 -m twine upload dist/*


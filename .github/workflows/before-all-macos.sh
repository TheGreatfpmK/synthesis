#!/bin/bash

# Inspired by build process of spead2

set -e -u

brew install ccache automake boost cln ginac glpk hwloc z3 xerces-c

# Install stormpy from PyPI or from local wheel if NIGHTLY_BUILD is set
if [[ "${NIGHTLY_BUILD:-false}" == "true" ]]; then
	echo "Installing stormpy from local wheel (nightly build)"
	PYTAG=$(python3 -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')")
	SOABI=$(python3 -c "import sysconfig; print(sysconfig.get_config_var('SOABI') or '')")
	WHEEL_DIR="${STORMPY_WHEEL_DIR:-$(pwd)/stormpy_wheels}"
	echo "Looking for stormpy wheels in: $WHEEL_DIR"
	ls -la "$WHEEL_DIR" || true
	if [[ "$PYTAG" == "314" && "$SOABI" == *"314t"* ]]; then
		WHEEL=$(ls "$WHEEL_DIR"/*-cp314-cp314t-*.whl 2>/dev/null | head -n 1 || true)
	else
		WHEEL=$(ls "$WHEEL_DIR"/*-cp${PYTAG}-cp${PYTAG}-*.whl 2>/dev/null | head -n 1 || true)
	fi
	if [[ -z "${WHEEL:-}" ]]; then
		echo "No matching stormpy wheel found for PYTAG=$PYTAG SOABI=$SOABI" >&2
		echo "Available wheels:" >&2
		ls -la "$WHEEL_DIR" >&2 || true
		exit 1
	fi
	echo "Installing stormpy wheel: $WHEEL"
	python3 -m pip install --force-reinstall "$WHEEL"
else
	echo "Installing stormpy from PyPI"
	python3 -m pip install stormpy
fi

# Query stormpy.info.storm_origin_info() and store into variables
read -r storm_repository storm_tag storm_commit_hash < <(
	python3 -c "import stormpy.info; print(*stormpy.info.storm_origin_info())"
)

# Install Storm
git clone "${storm_repository}"
cd storm
git checkout "${storm_commit_hash}"
mkdir build
cd build
cmake .. -DSTORM_BUILD_TESTS=OFF -DSTORM_BUILD_EXECUTABLES=OFF -DSTORM_PORTABLE=ON
make -j ${NR_JOBS}
sudo chown runner:admin /usr/local/ # Permission differ in macOS 14, see https://github.com/actions/runner-images/issues/9272
make install
cd ..
rm -rf build
#!/bin/bash

# Inspired by build process of spead2

set -e -u

dnf install -y boost-devel cln-devel gmp-devel glpk-devel hwloc-devel z3-devel xerces-c-devel eigen3-devel python3-devel # missing ginac

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

cd /tmp

# Install ginac
ginac_version=1.8.10
curl -fsSLO https://www.ginac.de/ginac-${ginac_version}.tar.bz2
tar -jxf ginac-${ginac_version}.tar.bz2
cd ginac-${ginac_version}
./configure CXXFLAGS="-O2"
make -j ${NR_JOBS}
make install
cd ..

# Install Boost 1.83 headers (no full build)
#
# Building all Boost libraries from source is extremely slow on GitHub-hosted Linux runners
# and is unnecessary for our use (we only need Boost headers at >= 1.83 for compilation).
BOOST_VERSION=1.83.0
BOOST_VERSION_UNDERSCORE=${BOOST_VERSION//./_}
BOOST_PREFIX=/opt/boost_${BOOST_VERSION_UNDERSCORE}
curl -fsSLO https://archives.boost.io/release/${BOOST_VERSION}/source/boost_${BOOST_VERSION_UNDERSCORE}.tar.gz
tar -xzf boost_${BOOST_VERSION_UNDERSCORE}.tar.gz
mkdir -p "${BOOST_PREFIX}/include"
cp -a "boost_${BOOST_VERSION_UNDERSCORE}/boost" "${BOOST_PREFIX}/include/"

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
make install
cd ..
rm -rf build
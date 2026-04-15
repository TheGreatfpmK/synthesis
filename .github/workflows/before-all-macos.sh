#!/bin/bash

# Inspired by build process of spead2

set -e -u

brew install ccache automake boost cln ginac glpk hwloc z3 xerces-c

PROJECT_DIR="${CIBW_PROJECT_DIR:-$PWD}"

# Install stormpy for querying which Storm version to build.
python3 -m pip install -U pip

WHEEL_DIR="${PROJECT_DIR}/stormpy_wheels"
if [[ -d "${WHEEL_DIR}" ]] && compgen -G "${WHEEL_DIR}/stormpy-*.whl" > /dev/null; then
	echo "Installing stormpy from local wheels in: ${WHEEL_DIR}"
	WHEEL=$(ls "${WHEEL_DIR}"/stormpy-*-cp310-*.whl 2>/dev/null | head -n 1 || true)
	if [[ -z "${WHEEL:-}" ]]; then
		WHEEL=$(ls "${WHEEL_DIR}"/stormpy-*.whl 2>/dev/null | head -n 1 || true)
	fi
	if [[ -z "${WHEEL:-}" ]]; then
		echo "No stormpy wheel found in ${WHEEL_DIR}" >&2
		exit 1
	fi
	python3 -m pip install --force-reinstall "${WHEEL}"
else
	if [[ -n "${STORMPY_VERSION:-}" ]]; then
		echo "Installing stormpy==${STORMPY_VERSION} from PyPI"
		python3 -m pip install "stormpy==${STORMPY_VERSION}"
	else
		echo "Installing stormpy from PyPI (latest)"
		python3 -m pip install stormpy
	fi
fi

echo "stormpy for origin query:"
python3 -c "import stormpy; print(stormpy.__version__, 'from', stormpy.__file__)"

STORM_ORIGIN=$(python3 -c "import stormpy.info; repo, tag, commit = stormpy.info.storm_origin_info(); print('{};{};{}'.format(repo or '', tag or '', commit or ''))")
STORM_REPO="${STORM_ORIGIN%%;*}"
REST="${STORM_ORIGIN#*;}"
STORM_TAG="${REST%%;*}"
STORM_COMMIT="${REST#*;}"

if [[ -n "${STORM_TAG}" ]]; then
	STORM_VERSION_RESOLVED="${STORM_TAG}"
elif [[ -n "${STORM_COMMIT}" ]]; then
	STORM_VERSION_RESOLVED="${STORM_COMMIT}"
else
	echo "Failed to determine Storm origin from stormpy (got: '${STORM_ORIGIN}')" >&2
	STORM_VERSION_RESOLVED="${STORM_VERSION:-master}"
fi

if [[ -z "${STORM_REPO}" ]]; then
	STORM_REPO="https://github.com/moves-rwth/storm.git"
fi

echo "Resolved Storm origin: repo='${STORM_REPO}', tag='${STORM_TAG}', commit='${STORM_COMMIT}'"
echo "Storm version to build: ${STORM_VERSION_RESOLVED}"

ORIGIN_FILE="${PROJECT_DIR}/.paynt_storm_origin.cmake"
cat > "${ORIGIN_FILE}" <<EOF
set(PAYNT_INFO_PRETEND_FETCH ON)
set(STORM_GIT_REPO "${STORM_REPO}")
set(STORM_GIT_TAG "${STORM_VERSION_RESOLVED}")
set(ALLOW_STORM_SYSTEM ON)
set(ALLOW_STORM_FETCH OFF)
set(STORM_DIR_HINT "/usr/local")
EOF
echo "Wrote Storm origin file: ${ORIGIN_FILE}"

# Install Storm
STORM_VERSION="${STORM_VERSION_RESOLVED}"

rm -rf storm
if git clone --depth 1 --branch "${STORM_VERSION}" "${STORM_REPO}" storm 2>/dev/null; then
	echo "Cloned Storm via --branch ${STORM_VERSION}"
else
	echo "Falling back to clone+checkout for Storm version '${STORM_VERSION}'"
	git clone "${STORM_REPO}" storm
	cd storm
	git checkout "${STORM_VERSION}"
	cd ..
fi

cd storm
mkdir build
cd build
cmake .. -DSTORM_BUILD_TESTS=OFF -DSTORM_BUILD_EXECUTABLES=OFF -DSTORM_PORTABLE=ON
make -j ${NR_JOBS}
sudo chown runner:admin /usr/local/ # Permission differ in macOS 14, see https://github.com/actions/runner-images/issues/9272
make install
cd ..
rm -rf build

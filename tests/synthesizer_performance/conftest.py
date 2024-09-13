
def pytest_addoption(parser):
    parser.addoption(
        "--generate-json", action="store_true", default=False, help="generate result json"
    )
    parser.addoption(
        "--overwrite-base", action="store_true", default=False, help="overwrite base result json"
    )
    parser.addoption(
        "--append-base", action="store_true", default=False, help="append base result json"
    )
    parser.addoption(
        "--synthesis-timeout", action="store", default=300, help="timeout for each synthesis run"
    )

generate_results_json = False
overwrite_base_results_json = False
append_base_results_json = False
synthesis_timeout = 300

def pytest_configure(config):
    global generate_results_json
    generate_results_json = config.getoption("--generate-json")
    global overwrite_base_results_json
    overwrite_base_results_json = config.getoption("--overwrite-base")
    global append_base_results_json
    append_base_results_json = config.getoption("--append-base")
    global synthesis_timeout
    synthesis_timeout = int(config.getoption("--synthesis-timeout"))

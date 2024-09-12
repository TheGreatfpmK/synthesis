
def pytest_addoption(parser):
    parser.addoption(
        "--generate", action="store_true", default=False, help="generate result json"
    )
    parser.addoption(
        "--overwrite", action="store_true", default=False, help="overwrite result json"
    )

generate_results_json = None
overwrite_results_json = None

def pytest_configure(config):
    global generate_results_json
    generate_results_json = config.option.generate
    global overwrite_results_json
    overwrite_results_json = config.option.overwrite

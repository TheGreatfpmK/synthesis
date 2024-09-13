import pytest

from conftest import generate_results_json, overwrite_base_results_json, append_base_results_json, synthesis_timeout

import json
import os
import itertools
import time
import psutil
import datetime

import paynt.quotient
import paynt.parser.sketch
import paynt.synthesizer.synthesizer


class TestSynthesizerPerformance:

    test_dir_path = os.path.abspath(os.path.dirname(__file__))

    models_path = test_dir_path + '/test_models.json'
    models_json = open(models_path, "r")
    models_info = json.loads(models_json.read())['models']
    models_json.close()

    synthesizers_path = test_dir_path + '/test_synthesizers.json'
    synthesizers_json = open(synthesizers_path, "r")
    synthesizers_info_all = json.loads(synthesizers_json.read())['synthesizers']
    synthesizers_info = [x for x in synthesizers_info_all if x['enabled'] == "True"]
    synthesizers_json.close()

    base_results_path = test_dir_path + '/base_results.json'
    base_results_json = open(base_results_path, "r")
    base_results_info = json.loads(base_results_json.read())
    base_results_json.close()

    test_info = itertools.product(models_info, synthesizers_info)

    results = {x['synthesizer_name']:[] for x in synthesizers_info}

    def init_quotient(self, model_info):
        sketch_path = self.test_dir_path + '/../../' + model_info['model_path'] + '/sketch.templ'
        properties_path = self.test_dir_path + '/../../' + model_info['model_path'] + '/sketch.props'
        return paynt.parser.sketch.Sketch.load_sketch(sketch_path, properties_path)

    def init_synthesizer(self, quotient, synthesizer_info):
        return paynt.synthesizer.synthesizer.Synthesizer.choose_synthesizer(quotient, synthesizer_info['method'])

    @pytest.mark.parametrize('model_info, synthesizer_info', test_info)
    @pytest.mark.timeout(synthesis_timeout)
    def test_performance(self, model_info, synthesizer_info):

        # skip test if base result exists and append option was used
        if append_base_results_json:
            models_in_results = [x['model'] for x in self.base_results_info[synthesizer_info['synthesizer_name']]]
            if model_info['name'] in models_in_results:
                pytest.skip("base result already exists")

        # for testing purposes if no base results exists skip the test
        if not append_base_results_json and not overwrite_base_results_json:
            models_in_results = [x['model'] for x in self.base_results_info[synthesizer_info['synthesizer_name']]]
            if model_info['name'] not in models_in_results:
                pytest.skip("base result does not exist, no performance comparison possible")

        # construct quotient 
        quotient = self.init_quotient(model_info)

        # setup the test environment for the given synthesizer
        if '--disable-expected-visits' in synthesizer_info['options']:
            paynt.quotient.quotient.Quotient.disable_expected_visits = True
        else:
            paynt.quotient.quotient.Quotient.disable_expected_visits = False

        # create synthesizer
        synthesizer = self.init_synthesizer(quotient, synthesizer_info)

        # run the synthesis
        synthesizer.synthesize(keep_optimum=True)

        # store results
        performance_result = {'model': model_info['name'],
                              'family_size': synthesizer.stat.quotient.family.size,
                              'iterations_dtmc': synthesizer.stat.iterations_dtmc,
                              'avg_size_dtmc': round(synthesizer.stat.acc_size_dtmc, synthesizer.stat.iterations_dtmc) if synthesizer.stat.iterations_dtmc is not None else None,
                              'iterations_mdp': synthesizer.stat.iterations_mdp,
                              'avg_size_mdp': round(synthesizer.stat.acc_size_mdp, synthesizer.stat.iterations_mdp) if synthesizer.stat.iterations_mdp is not None else None,
                              'iterations_game': synthesizer.stat.iterations_game,
                              'avg_size_game': round(synthesizer.stat.acc_size_game, synthesizer.stat.iterations_game) if synthesizer.stat.iterations_game is not None else None,
                              'explored': synthesizer.explored,
                              'synthesis_time': synthesizer.stat.synthesis_timer.time,
                              'optimum': round(synthesizer.stat.quotient.specification.optimality.optimum, 6) if synthesizer.stat.quotient.specification.optimality.optimum is not None else None,
                              'timestamp': str(datetime.datetime.now())
                              }
        self.results[synthesizer_info['synthesizer_name']].append(performance_result)

        # check performance
        if not append_base_results_json and not overwrite_base_results_json:
            base_data = [x for x in self.base_results_info[synthesizer_info['synthesizer_name']] if x['model'] == model_info['name']]
            base_data = base_data[0]
            if base_data['optimum'] is not None:
                assert performance_result['optimum'] == base_data['optimum'], 'the tested implementation returned different optimum value'
            if base_data['iterations_dtmc'] is not None:
                assert performance_result['iterations_dtmc'] <= base_data['iterations_dtmc'], 'the tested implementation performed more iterations!'
            if base_data['iterations_mdp'] is not None:
                assert performance_result['iterations_mdp'] <= base_data['iterations_mdp'], 'the tested implementation performed more iterations!'
            if base_data['iterations_game'] is not None:
                assert performance_result['iterations_game'] <= base_data['iterations_dtmc'], 'the tested implementation performed more iterations!'

    @classmethod
    def teardown_class(self):
        # base results updates
        if overwrite_base_results_json:
            result_file = open(self.test_dir_path + f"/base_results.json", 'w')
            json.dump(self.results, result_file, indent=4)
            result_file.close()
        elif append_base_results_json:
            result_file = open(self.test_dir_path + f"/base_results.json", 'w')
            for method, data in self.results.items():
                # if method was not in base results, add the entry for this new method
                if method not in self.base_results_info.keys():
                    self.base_results_info[method] = []
                base_data = self.base_results_info[method]
                base_data_models = [x['model'] for x in base_data]
                for model_data in data:
                    if model_data['model'] not in base_data_models:
                        self.base_results_info[method].append(model_data)
            json.dump(self.base_results_info, result_file, indent=4)
            result_file.close()

        # test results generation
        timestamp = str(datetime.datetime.now()).split('.')[0].replace(' ', '_').replace('-', '_').replace(':', '_')

        if generate_results_json:
            result_file = open(self.test_dir_path + f"/performance_results_{timestamp}.json", 'w')
            json.dump(self.results, result_file, indent=4)
            result_file.close()
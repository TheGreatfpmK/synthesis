#include "../synthesis.h"

#include "storm/storage/Scheduler.h"
#include "storm/storage/BitVector.h"

#include <unordered_set>

namespace synthesis
{
    template <typename PredicateFactory>
    void fillPredicateEvaluation(
        storm::storage::BitVector& valuation,
        const std::vector<std::vector<uint64_t>>& stateValuations,
        PredicateFactory&& predicate)
    {
        const size_t numStates = stateValuations.size();
        for (size_t state = 0; state < numStates; ++state) {
            if (predicate(stateValuations[state])) {
                valuation.set(state);
            }
        }
    }

    storm::storage::Scheduler<double> createScheduler(uint_fast64_t numberOfModelStates) {
        return storm::storage::Scheduler<double>(numberOfModelStates);
    }

    void setDontCareStateForScheduler(storm::storage::Scheduler<double>& scheduler, uint_fast64_t modelState, uint_fast64_t memoryState, bool setArbitraryChoice) {
        scheduler.setDontCare(modelState, memoryState, setArbitraryChoice);
    }

    std::map<std::string, storm::storage::BitVector> getAtomicPredicateEvals(uint64_t nrStates, const std::vector<std::string>& variableNames, const std::vector<std::vector<uint64_t>>& variableDomains, const std::vector<std::vector<uint64_t>>& stateValuations, bool defaultPredicates = false) {

        std::map<std::string, storm::storage::BitVector> predicateToValuation;
        const size_t numStates = stateValuations.size();
        const size_t numVariables = variableNames.size();
        
        if (defaultPredicates) {
            for (size_t i = 0; i < numVariables; ++i) {
                for (size_t j = 0; j < variableDomains[i].size(); ++j) {
                    std::string predicateName = variableNames[i] + "<=" + std::to_string(variableDomains[i][j]);
                    storm::storage::BitVector bitVector(nrStates);
                    for (size_t k = 0; k < numStates; ++k) {
                        if (stateValuations[k][i] <= variableDomains[i][j]) {
                            bitVector.set(k);
                        }
                    }
                    predicateToValuation[predicateName] = bitVector;
                }
            }

            return predicateToValuation;
        }

        // Non-default predicates
        auto deduplicateByValue = [&]() {
            std::map<std::string, storm::storage::BitVector> uniquePredicates;
            std::unordered_set<storm::storage::BitVector> seenValues;
            for (auto const& entry : predicateToValuation) {
                const auto setBits = entry.second.getNumberOfSetBits();
                if (setBits == 0 || setBits == entry.second.size()) {
                    continue;
                }
                if (seenValues.insert(entry.second).second && seenValues.insert(~entry.second).second) {
                    uniquePredicates.emplace(entry.first, entry.second);
                }
            }
            predicateToValuation.swap(uniquePredicates);
        };

        // constant comparisons: ==, !=, <, <=, >, >=
        std::map<std::string, std::function<bool(uint64_t, uint64_t)>> compOps;
        compOps["=="] = [](uint64_t a, uint64_t b){ return a == b; };
        // compOps["!="] = [](uint64_t a, uint64_t b){ return a != b; };
        // compOps["<"]  = [](uint64_t a, uint64_t b){ return a < b; };
        compOps["<="] = [](uint64_t a, uint64_t b){ return a <= b; };
        // compOps[">"]  = [](uint64_t a, uint64_t b){ return a > b; };
        compOps[">="] = [](uint64_t a, uint64_t b){ return a >= b; };

        // variable vs constant predicates
        for (size_t var_id = 0; var_id < numVariables; ++var_id) {
            const auto& domain_list = variableDomains[var_id];
            const size_t domain_end = domain_list.empty() ? 0 : domain_list.size() - 1;
            for (size_t di = 0; di < domain_end; ++di) {
                uint64_t constant = domain_list[di];
                for (auto const& kv : compOps) {
                    const std::string& op_str = kv.first;
                    auto op_func = kv.second;
                    std::string key = variableNames[var_id] + op_str + std::to_string(constant);
                    auto insertResult = predicateToValuation.emplace(key, storm::storage::BitVector(nrStates));
                    auto& valuation = insertResult.first->second;
                    fillPredicateEvaluation(valuation, stateValuations, [&](const std::vector<uint64_t>& state) {
                        return op_func(state[var_id], constant);
                    });
                }
            }
        }

        // variable vs variable comparisons
        std::map<std::string, std::function<bool(uint64_t, uint64_t)>> varComp = compOps;
        for (size_t i = 0; i < numVariables; ++i) {
            for (size_t j = i + 1; j < numVariables; ++j) {
                for (auto const& kv : varComp) {
                    const std::string& op_str = kv.first;
                    auto op_func = kv.second;
                    std::string key = variableNames[i] + op_str + variableNames[j];
                    auto insertResult = predicateToValuation.emplace(key, storm::storage::BitVector(nrStates));
                    auto& valuation = insertResult.first->second;
                    fillPredicateEvaluation(valuation, stateValuations, [&](const std::vector<uint64_t>& state) {
                        return op_func(state[i], state[j]);
                    });
                }
            }
        }

        // interval predicates: constant1 <= var <= constant2
        for (size_t var_id = 0; var_id < numVariables; ++var_id) {
            const auto& domain_list = variableDomains[var_id];
            const size_t domain_end = domain_list.empty() ? 0 : domain_list.size() - 1;
            for (size_t i = 0; i < domain_end; ++i) {
                for (size_t j = 0; j < domain_end; ++j) {
                    uint64_t c1 = domain_list[i];
                    uint64_t c2 = domain_list[j];
                    if (c1 >= c2) continue;
                    std::string key = std::to_string(c1) + "<=" + variableNames[var_id] + "<=" + std::to_string(c2);
                    auto insertResult = predicateToValuation.emplace(key, storm::storage::BitVector(nrStates));
                    auto& valuation = insertResult.first->second;
                    fillPredicateEvaluation(valuation, stateValuations, [&](const std::vector<uint64_t>& state) {
                        const uint64_t value = state[var_id];
                        return value >= c1 && value <= c2;
                    });
                }
            }
        }

        // max variable predicates
        for (size_t var_id = 0; var_id < numVariables; ++var_id) {
            std::string key = std::string("max_variable==") + variableNames[var_id];
            auto insertResult = predicateToValuation.emplace(key, storm::storage::BitVector(nrStates));
            auto& valuation = insertResult.first->second;
            fillPredicateEvaluation(valuation, stateValuations, [&](const std::vector<uint64_t>& state) {
                const uint64_t value = state[var_id];
                for (size_t other = 0; other < numVariables; ++other) {
                    if (state[other] > value) {
                        return false;
                    }
                }
                return true;
            });
        }

        // logical combinations of two predicates (AND/OR)
        deduplicateByValue(); // deduplicate before creating combinations to reduce the number of combinations
        std::vector<std::string> LOGICAL_OPERATORS = {"AND", "OR"};
        std::vector<std::string> existing_predicates;
        existing_predicates.reserve(predicateToValuation.size());
        for (auto const& p : predicateToValuation) existing_predicates.push_back(p.first);

        for (size_t i = 0; i < existing_predicates.size(); ++i) {
            for (size_t j = i+1; j < existing_predicates.size(); ++j) {
                const std::string &pred1 = existing_predicates[i];
                const std::string &pred2 = existing_predicates[j];
                const auto &val1 = predicateToValuation.at(pred1);
                const auto &val2 = predicateToValuation.at(pred2);
                for (auto const& op : LOGICAL_OPERATORS) {
                    std::string new_pred = std::string("(") + pred1 + " " + op + " " + pred2 + ")";
                    if (predicateToValuation.find(new_pred) == predicateToValuation.end()) {
                        predicateToValuation.emplace(new_pred, storm::storage::BitVector(nrStates));
                    }
                    auto &new_val = predicateToValuation.at(new_pred);
                    if (op == "AND") {
                        new_val = val1 & val2;
                    } else if (op == "OR") {
                        new_val = val1 | val2;
                    }
                }
            }
        }

        deduplicateByValue();

        return predicateToValuation;
    }
}

void bindings_storage(py::module& m) {
    
    m.def("create_scheduler", &synthesis::createScheduler, py::arg("number_of_model_states"));
    m.def("set_dont_care_state_for_scheduler", &synthesis::setDontCareStateForScheduler, py::arg("scheduler"), py::arg("model_state"), py::arg("memory_state"), py::arg("set_arbitrary_choice"));
    m.def("get_atomic_predicate_evals", &synthesis::getAtomicPredicateEvals, py::arg("nr_states"), py::arg("variable_names"), py::arg("variable_domains"), py::arg("state_valuations"), py::arg("default_predicates") = false);
}
#include "modelchecking.h"
#include "result.h"
#include "storm/models/symbolic/StandardRewardModel.h"
#include "storm/modelchecker/results/CheckResult.h"
#include "storm/modelchecker/csl/helper/SparseCtmcCslHelper.h"
#include "storm/environment/Environment.h"

template<typename ValueType>
using CheckTask = storm::modelchecker::CheckTask<storm::logic::Formula, ValueType>;

// Thin wrapper for model checking using sparse engine
template<typename ValueType>
std::shared_ptr<storm::modelchecker::CheckResult> modelCheckingSparseEngine(std::shared_ptr<storm::models::sparse::Model<ValueType>> model, CheckTask<ValueType> const& task, storm::Environment const& env) {
    return storm::api::verifyWithSparseEngine<ValueType>(env, model, task);
}

template<typename ValueType>
std::shared_ptr<storm::modelchecker::CheckResult> modelCheckingSparseEngineMdpFamilies(std::shared_ptr<storm::models::sparse::Mdp<ValueType>> family, CheckTask<ValueType> const& task, std::vector<std::vector<uint_fast64_t>> const& subfamilies, std::vector<storm::storage::BitVector> const& initValues, storm::Environment const& env) {
    return storm::api::verifyWithSparseEngineMdpFamilies<ValueType>(env, family, task, subfamilies, initValues);
}

template<typename ValueType>
std::shared_ptr<storm::modelchecker::CheckResult> modelCheckingFullyObservableSparseEngine(std::shared_ptr<storm::models::sparse::Pomdp<ValueType>> model, CheckTask<ValueType> const& task, storm::Environment const& env) {
    return storm::api::verifyWithSparseEngine<ValueType>(env, model->template as<storm::models::sparse::Mdp<ValueType>>(), task);
}

// Thin wrapper for model checking using dd engine
template<storm::dd::DdType DdType, typename ValueType>
std::shared_ptr<storm::modelchecker::CheckResult> modelCheckingDdEngine(std::shared_ptr<storm::models::symbolic::Model<DdType, ValueType>> model, CheckTask<ValueType> const& task, storm::Environment const& env) {
    return storm::api::verifyWithDdEngine<DdType, ValueType>(env, model, task);
}

// Thin wrapper for model checking using hybrid engine
template<storm::dd::DdType DdType, typename ValueType>
std::shared_ptr<storm::modelchecker::CheckResult> modelCheckingHybridEngine(std::shared_ptr<storm::models::symbolic::Model<DdType, ValueType>> model, CheckTask<ValueType> const& task, storm::Environment const& env) {
    return storm::api::verifyWithHybridEngine<DdType, ValueType>(env, model, task);
}

std::vector<double> computeAllUntilProbabilities(storm::Environment const& env, CheckTask<double> const& task, std::shared_ptr<storm::models::sparse::Ctmc<double>> ctmc, storm::storage::BitVector const& phiStates, storm::storage::BitVector const& psiStates) {
    storm::solver::SolveGoal<double> goal(*ctmc, task);
    return storm::modelchecker::helper::SparseCtmcCslHelper::computeAllUntilProbabilities(env, std::move(goal), ctmc->getTransitionMatrix(), ctmc->getExitRateVector(), ctmc->getInitialStates(), phiStates, psiStates);
}

std::vector<double> computeTransientProbabilities(storm::Environment const& env, std::shared_ptr<storm::models::sparse::Ctmc<double>> ctmc, storm::storage::BitVector const& phiStates, storm::storage::BitVector const& psiStates, double timeBound) {
    return storm::modelchecker::helper::SparseCtmcCslHelper::computeAllTransientProbabilities(env, ctmc->getTransitionMatrix(), ctmc->getInitialStates(), phiStates, psiStates, ctmc->getExitRateVector(), timeBound);
}


// Thin wrapper for computing prob01 states
template<typename ValueType>
std::pair<storm::storage::BitVector, storm::storage::BitVector> computeProb01(storm::models::sparse::Dtmc<ValueType> const& model, storm::storage::BitVector const& phiStates, storm::storage::BitVector const& psiStates) {
    return storm::utility::graph::performProb01(model, phiStates, psiStates);
}

template<typename ValueType>
std::pair<storm::storage::BitVector, storm::storage::BitVector> computeProb01min(storm::models::sparse::Mdp<ValueType> const& model, storm::storage::BitVector const& phiStates, storm::storage::BitVector const& psiStates) {
    return storm::utility::graph::performProb01Min(model, phiStates, psiStates);
}

template<typename ValueType>
std::pair<storm::storage::BitVector, storm::storage::BitVector> computeProb01max(storm::models::sparse::Mdp<ValueType> const& model, storm::storage::BitVector const& phiStates, storm::storage::BitVector const& psiStates) {
    return storm::utility::graph::performProb01Max(model, phiStates, psiStates);
}

// Define python bindings
void define_modelchecking(py::module& m) {

    // CheckTask
    py::class_<CheckTask<double>, std::shared_ptr<CheckTask<double>>>(m, "CheckTask", "Task for model checking")
    //m.def("create_check_task", &storm::api::createTask, "Create task for verification", py::arg("formula"), py::arg("only_initial_states") = false);
        .def(py::init<storm::logic::Formula const&, bool>(), py::arg("formula"), py::arg("only_initial_states") = false)
        .def("set_produce_schedulers", &CheckTask<double>::setProduceSchedulers, "Set whether schedulers should be produced (if possible)", py::arg("produce_schedulers") = true)
    ;
    // CheckTask
    py::class_<CheckTask<storm::RationalNumber>, std::shared_ptr<CheckTask<storm::RationalNumber>>>(m, "ExactCheckTask", "Task for model checking with exact numbers")
            //m.def("create_check_task", &storm::api::createTask, "Create task for verification", py::arg("formula"), py::arg("only_initial_states") = false);
            .def(py::init<storm::logic::Formula const&, bool>(), py::arg("formula"), py::arg("only_initial_states") = false)
            .def("set_produce_schedulers", &CheckTask<storm::RationalNumber>::setProduceSchedulers, "Set whether schedulers should be produced (if possible)", py::arg("produce_schedulers") = true)
            ;
    py::class_<CheckTask<storm::RationalFunction>, std::shared_ptr<CheckTask<storm::RationalFunction>>>(m, "ParametricCheckTask", "Task for parametric model checking")
    //m.def("create_check_task", &storm::api::createTask, "Create task for verification", py::arg("formula"), py::arg("only_initial_states") = false);
        .def(py::init<storm::logic::Formula const&, bool>(), py::arg("formula"), py::arg("only_initial_states") = false)
        .def("set_produce_schedulers", &CheckTask<storm::RationalFunction>::setProduceSchedulers, "Set whether schedulers should be produced (if possible)", py::arg("produce_schedulers") = true)
    ;

    // Model checking
    m.def("_model_checking_fully_observable", &modelCheckingFullyObservableSparseEngine<double>, py::arg("model"), py::arg("task"), py::arg("environment")  = storm::Environment());
    m.def("_exact_model_checking_fully_observable", &modelCheckingFullyObservableSparseEngine<storm::RationalNumber>, py::arg("model"), py::arg("task"), py::arg("environment")  = storm::Environment());
    m.def("_model_checking_sparse_engine", &modelCheckingSparseEngine<double>, "Perform model checking using the sparse engine", py::arg("model"), py::arg("task"), py::arg("environment") = storm::Environment());
    m.def("_model_checking_sparse_engine_mdp_families", &modelCheckingSparseEngineMdpFamilies<double>, "Perform model checking of multiple families (CEGAR) using the sparse engine", py::arg("family"), py::arg("task"), py::arg("subfamilies"), py::arg("initValues"), py::arg("environment") = storm::Environment());
    m.def("_exact_model_checking_sparse_engine",  &modelCheckingSparseEngine<storm::RationalNumber>, "Perform model checking using the sparse engine", py::arg("model"), py::arg("task"), py::arg("environment") = storm::Environment());
    m.def("_parametric_model_checking_sparse_engine", &modelCheckingSparseEngine<storm::RationalFunction>, "Perform parametric model checking using the sparse engine", py::arg("model"), py::arg("task"), py::arg("environment") = storm::Environment());
    m.def("_model_checking_dd_engine", &modelCheckingDdEngine<storm::dd::DdType::Sylvan, double>, "Perform model checking using the dd engine", py::arg("model"), py::arg("task"), py::arg("environment") = storm::Environment());
    m.def("_parametric_model_checking_dd_engine", &modelCheckingDdEngine<storm::dd::DdType::Sylvan, storm::RationalFunction>, "Perform parametric model checking using the dd engine", py::arg("model"), py::arg("task"), py::arg("environment") = storm::Environment());
    m.def("_model_checking_hybrid_engine", &modelCheckingHybridEngine<storm::dd::DdType::Sylvan, double>, "Perform model checking using the hybrid engine", py::arg("model"), py::arg("task"), py::arg("environment") = storm::Environment());
    m.def("_parametric_model_checking_hybrid_engine", &modelCheckingHybridEngine<storm::dd::DdType::Sylvan, storm::RationalFunction>, "Perform parametric model checking using the hybrid engine", py::arg("model"), py::arg("task"), py::arg("environment") = storm::Environment());
    m.def("compute_all_until_probabilities", &computeAllUntilProbabilities, "Compute forward until probabilities");
    m.def("compute_transient_probabilities", &computeTransientProbabilities, "Compute transient probabilities");
    m.def("_compute_prob01states_double", &computeProb01<double>, "Compute prob-0-1 states", py::arg("model"), py::arg("phi_states"), py::arg("psi_states"));
    m.def("_compute_prob01states_rationalfunc", &computeProb01<storm::RationalFunction>, "Compute prob-0-1 states", py::arg("model"), py::arg("phi_states"), py::arg("psi_states"));
    m.def("_compute_prob01states_min_double", &computeProb01min<double>, "Compute prob-0-1 states (min)", py::arg("model"), py::arg("phi_states"), py::arg("psi_states"));
    m.def("_compute_prob01states_max_double", &computeProb01max<double>, "Compute prob-0-1 states (max)", py::arg("model"), py::arg("phi_states"), py::arg("psi_states"));
    m.def("_compute_prob01states_min_rationalfunc", &computeProb01min<storm::RationalFunction>, "Compute prob-0-1 states (min)", py::arg("model"), py::arg("phi_states"), py::arg("psi_states"));
    m.def("_compute_prob01states_max_rationalfunc", &computeProb01max<storm::RationalFunction>, "Compute prob-0-1 states (max)", py::arg("model"), py::arg("phi_states"), py::arg("psi_states"));
}

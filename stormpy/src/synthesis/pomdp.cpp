#include "synthesis.h"

#include "storm-synthesis/pomdp/ExplicitPomdpMemoryUnfolder.h"
#include "storm-synthesis/pomdp/PomdpManager.h"

#include "storm/storage/SparseMatrix.h"

// Define python bindings
void define_pomdp(py::module& m) {

    py::class_<storm::synthesis::ExplicitPomdpMemoryUnfolder<double>>(m, "ExplicitPomdpMemoryUnfolder", "Explicit memory unfolder for POMDPs")
        .def(py::init<storm::models::sparse::Pomdp<double> const&, storm::storage::PomdpMemory const&>(), "Constructor.", py::arg("pomdp"), py::arg("memory"))
        .def("transform", &storm::synthesis::ExplicitPomdpMemoryUnfolder<double>::transform, "Unfold memory into POMDP.")
        .def("state_to_state", &storm::synthesis::ExplicitPomdpMemoryUnfolder<double>::state_to_state, "TODO")
        .def("state_to_memory", &storm::synthesis::ExplicitPomdpMemoryUnfolder<double>::state_to_memory, "TODO")
        ;

    py::class_<storm::synthesis::PomdpManager<double>>(m, "PomdpManager", "POMDP manager")
        .def(py::init<storm::models::sparse::Pomdp<double> const&>(), "Constructor.", py::arg("pomdp"))
        .def("construct_mdp", &storm::synthesis::PomdpManager<double>::constructMdp, "Unfold POMDP into MDP.")
        .def("inject_memory", &storm::synthesis::PomdpManager<double>::injectMemory, "Inject 1 state into a selected observation.", py::arg("observation"))
        .def("set_memory_size", &storm::synthesis::PomdpManager<double>::setMemorySize, "Set memory size to all observations.", py::arg("memory_size"))
        .def_property_readonly("observation_memory_size", [](storm::synthesis::PomdpManager<double>& manager) {return manager.observation_memory_size;}, "TODO")
        .def_property_readonly("observation_actions", [](storm::synthesis::PomdpManager<double>& manager) {return manager.observation_actions;}, "TODO")
        .def_property_readonly("prototype_row_index", [](storm::synthesis::PomdpManager<double>& manager) {return manager.prototype_row_index;}, "TODO")
        .def_property_readonly("num_holes", [](storm::synthesis::PomdpManager<double>& manager) {return manager.num_holes;}, "TODO")
        .def_property_readonly("action_holes", [](storm::synthesis::PomdpManager<double>& manager) {return manager.action_holes;}, "TODO")
        .def_property_readonly("memory_holes", [](storm::synthesis::PomdpManager<double>& manager) {return manager.memory_holes;}, "TODO")
        .def_property_readonly("hole_options", [](storm::synthesis::PomdpManager<double>& manager) {return manager.hole_options;}, "TODO")
        .def_property_readonly("row_action_hole", [](storm::synthesis::PomdpManager<double>& manager) {return manager.row_action_hole;}, "TODO")
        .def_property_readonly("row_action_option", [](storm::synthesis::PomdpManager<double>& manager) {return manager.row_action_option;}, "TODO")
        .def_property_readonly("row_memory_hole", [](storm::synthesis::PomdpManager<double>& manager) {return manager.row_memory_hole;}, "TODO")
        .def_property_readonly("row_memory_option", [](storm::synthesis::PomdpManager<double>& manager) {return manager.row_memory_option;}, "TODO")
        ;

    m.def("multiply_with_vector", [] (storm::storage::SparseMatrix<double> matrix,std::vector<double> vector) {
        std::vector<double> result(matrix.getRowCount());
        matrix.multiplyWithVector(vector, result);
        return result;
    }, py::arg("matrix"), py::arg("vector"));
}



#include "../synthesis.h"

#include "ConditionalUnfolder.h"

template <typename ValueType>
void bindings_unfolder_vt(py::module &m, std::string const& vtSuffix) {

    py::class_<synthesis::ConditionalUnfolder<ValueType>>(m, (vtSuffix + "ConditionalUnfolder").c_str(), "Conditional Unfolder class")
        .def(py::init<storm::models::sparse::Mdp<ValueType> const&, storm::logic::ConditionalFormula const&>(), "Constructor.", py::arg("mdp"), py::arg("formula"))
        .def("construct_unfolded_model", &synthesis::ConditionalUnfolder<ValueType>::constructUnfoldedModel,
            "Construct an unfolded MDP from a given MDP and conditional formula."
        )
        .def("map_scheduler_to_quotient", &synthesis::ConditionalUnfolder<ValueType>::map_scheduler_to_quotient,
            "Map a scheduler from the unfolded MDP to the quotient MDP.",
            py::arg("model_matrix"),
            py::arg("quotient_state_map"),
            py::arg("quotient_choice_map"),
            py::arg("scheduler"),
            py::arg("reach_target_choices"),
            py::arg("reach_condition_choices")
        )
        .def_property_readonly("conditional_states", [](synthesis::ConditionalUnfolder<ValueType>& unfolder) {return unfolder.getConditionalStatesForOriginalModel();})
        .def_property_readonly("target_states", [](synthesis::ConditionalUnfolder<ValueType>& unfolder) {return unfolder.getTargetStatesForOriginalModel();})
        .def_property_readonly("conditional_label", [](synthesis::ConditionalUnfolder<ValueType>& unfolder) {return unfolder.getConditionalLabel();})
        .def_property_readonly("target_label", [](synthesis::ConditionalUnfolder<ValueType>& unfolder) {return unfolder.getTargetLabel();})
        .def_property_readonly("state_prototype", [](synthesis::ConditionalUnfolder<ValueType>& unfolder) {return unfolder.statePrototype;})
        .def_property_readonly("state_memory", [](synthesis::ConditionalUnfolder<ValueType>& unfolder) {return unfolder.stateMemory;})
        .def_property_readonly("choice_map", [](synthesis::ConditionalUnfolder<ValueType>& unfolder) {return unfolder.choiceMap;})
        ;
}

void bindings_unfolder(py::module& m) {
    bindings_unfolder_vt<double>(m, "");
    bindings_unfolder_vt<storm::RationalNumber>(m, "Exact");
}
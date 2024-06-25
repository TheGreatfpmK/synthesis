#include "../synthesis.h"

#include "StochasticGame.h"

void bindings_stochastic_games(py::module& m) {

    py::class_<synthesis::StochasticGame>(m, "StochasticGame", "test")
        .def(py::init<storm::models::sparse::Pomdp<double> const&>(), "Constructor.")
        .def("build_game", &synthesis::StochasticGame::buildGame, "build multiplayer game")
        .def("check_game", &synthesis::StochasticGame::checkGame, py::arg("game"), "check multiplayer game")
        ;
}


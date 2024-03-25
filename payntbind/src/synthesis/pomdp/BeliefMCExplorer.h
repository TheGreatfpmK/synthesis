#pragma once

#include <vector>
#include <map>

#include <storm/models/sparse/Pomdp.h>
#include <storm/models/sparse/Dtmc.h>
#include <storm-pomdp/storage/BeliefManager.h>
#include <storm-pomdp/builder/BeliefMdpExplorer.h>
#include <storm/utility/ConstantsComparator.h>
#include <storm/logic/Formula.h>
#include <storm-pomdp/modelchecker/BeliefExplorationPomdpModelChecker.h>
#include <storm-pomdp/modelchecker/PreprocessingPomdpValueBoundsModelChecker.h>

namespace synthesis {

    class AlphaVectorSet {
        using AlphaVector = std::vector<double>;

        public:

            AlphaVectorSet(std::vector<AlphaVector> const& alphaVectors, std::vector<uint64_t> const& alphaVectorActions) {
                this->alphaVectors = alphaVectors;
                this->alphaVectorActions = alphaVectorActions;
            }

            std::vector<AlphaVector> alphaVectors;
            std::vector<uint64_t> alphaVectorActions;
    };
    
    template<typename PomdpModelType, typename BeliefValueType = typename PomdpModelType::ValueType, typename BeliefMDPType = typename PomdpModelType::ValueType>
    class BeliefMCExplorer {

        typedef storm::storage::BeliefManager<PomdpModelType, BeliefValueType> BeliefManagerType;
        typedef storm::builder::BeliefMdpExplorer<PomdpModelType, BeliefValueType> ExplorerType;
        typedef typename PomdpModelType::ValueType PomdpValueType;

        public:

            BeliefMCExplorer(std::shared_ptr<PomdpModelType> pomdp);

            double checkAlphaVectors(storm::logic::Formula const& formula, AlphaVectorSet const& alphaVectorSet);

            double checkAlphaVectors(storm::logic::Formula const& formula, AlphaVectorSet const& alphaVectorSet, storm::Environment const& env);

        private:

            PomdpModelType const& pomdp() const;

            bool exploreMC(std::set<uint32_t> const &targetObservations, bool min, bool computeRewards, std::shared_ptr<BeliefManagerType>& beliefManager, std::shared_ptr<ExplorerType>& beliefExplorer, std::vector<typename PomdpModelType::ValueType> const &cutoffVec, AlphaVectorSet const& alphaVectorSet,
            storm::Environment const& env);

            uint64_t getBestActionInBelief(uint64_t beliefId, std::shared_ptr<BeliefManagerType> &beliefManager, std::shared_ptr<ExplorerType> &beliefExplorer, AlphaVectorSet const& alphaVectorSet);

            std::shared_ptr<PomdpModelType> inputPomdp;
            std::shared_ptr<PomdpModelType> preprocessedPomdp;

            double precision;

            storm::pomdp::modelchecker::POMDPValueBounds<BeliefValueType> pomdpValueBounds;

    };
}
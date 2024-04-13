import stormpy

from .statistic import Statistic
from .synthesizer_ar import SynthesizerAR
from .synthesizer_ar_storm import SynthesizerARStorm
from .synthesizer_hybrid import SynthesizerHybrid
from .synthesizer_multicore_ar import SynthesizerMultiCoreAR

from ..quotient.models import MarkovChain, DTMC, MDP

import paynt.quotient.quotient
import paynt.quotient.pomdp
from ..utils.profiler import Timer

import paynt.verification.property

import math
from collections import defaultdict

from threading import Thread
from queue import Queue
import time

import logging 
logger = logging.getLogger(__name__)



class SynthesizerDECPOMDP(paynt.synthesizer.synthesizer_ar.SynthesizerAR):

    def run(self, optimum_threshold=None, export_evaluation=None):
        self.strategy_iterative(optimum_threshold,unfold_imperfect_only=True)


    def strategy_iterative(self,optimum_threshold, unfold_imperfect_only):
        '''
        @param unfold_imperfect_only if True, only imperfect observations will be unfolded
        '''
        # self.quotient.set_imperfect_memory_size(1)
        # self.synthesize(self.quotient.design_space,optimum_threshold=optimum_threshold)
        # print("OPTIMUM/////////////////////////////////1",self.quotient.specification.optimality.optimum)
        # self.quotient.set_imperfect_memory_size(2)
        # self.synthesize(self.quotient.design_space,optimum_threshold=optimum_threshold)
        # print("OPTIMUM/////////////////////////////////2",self.quotient.specification.optimality.optimum)
        # self.quotient.set_imperfect_memory_size(3)
        # self.synthesize(self.quotient.design_space,optimum_threshold=optimum_threshold)
            
        mem_size = paynt.quotient.pomdp.PomdpQuotient.initial_memory_size
        opt = self.quotient.specification.optimality.optimum
        while True:
            # print("MEM SIZE>>>>>>>>>>>>>>>>>>>>>>>>>",mem_size)
            
            logger.info("Synthesizing optimal k={} controller ...".format(mem_size) )
            if unfold_imperfect_only:
                self.quotient.set_imperfect_memory_size(mem_size)
            else:
                self.quotient.set_global_memory_size(mem_size)
            
            self.synthesize(self.quotient.design_space,optimum_threshold=optimum_threshold)

            opt_old = opt
            opt = self.quotient.specification.optimality.optimum

            # finish if optimum has not been improved
            # if opt_old == opt and opt is not None:
            #     break
            mem_size += 1
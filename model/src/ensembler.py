'''
    File to have an ensembler class.
    WIP.
'''

__author__ = 'haroun habeeb'
__mail__ = 'haroun7@gmail.com'
# general imports
import argparse
import pickle
import os
import sys
import pdb
import numpy as np
import logging
import nltk
import re
# pytorch imports
import torch
import torch.utils.data
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.autograd import Variable
from torch.distributions import Bernoulli
# Custom imports
from .utils import tensordot


class Ensembler(torch.nn.Module):
    def __init__(self, model_list, args):
        self.model_list = model_list
        self.args = args
        # TODO: set up ensembling
        self.ensemble_method = args.ensemble_method

    def forward(self, x):
        predictions = []
        for model in self.model_list:
            predictions.append(model(x))
        predictions = torch.from_numpy(np.array(predictions))
        # Go through voting
        if self.ensemble_method == 'median':
            result = torch.median(predictions)
        elif self.ensemble_method == 'mean':
            result = torch.mean(predictions)
        else:
            result = None
        return result

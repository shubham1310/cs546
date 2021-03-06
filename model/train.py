#!/usr/bin/env python

import os
import argparse
import logging
import numpy as np
import scipy
from time import time
import sys
import pdb
import pickle as pk
# pytorch imports
import torch
import torch.utils.data
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.autograd import Variable
from torch.distributions import Bernoulli
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence
# User imports
from src.model import Model, EnsembleModel
from src.dataset import ASAPDataset, ASAPDataLoader
import src.utils as U
from tensorboard_logger import configure, log_value

logger = logging.getLogger(__name__)

# parsing arguments

parser = argparse.ArgumentParser()
parser.add_argument('--compressed_datasets', type=str, default='', help='pkl file to load dataset objects from')
parser.add_argument('--nm', type=str, default='new', help='Name to save logs')
parser.add_argument("--ensembles", dest="ensemble_models", type=str, nargs='+', metavar='<str>', default=None, help="List of torch.save models to use in ensemble")
parser.add_argument("--ensemble-method", dest="ensemble_method", type=str, metavar='<str>', default='mean', help="Method to ensemble (default=mean)")
parser.add_argument("-tr", "--train", dest="train_path", type=str, metavar='<str>', required=True, help="The path to the training set")
parser.add_argument("-tu", "--tune", dest="dev_path", type=str, metavar='<str>', required=True, help="The path to the development set")
parser.add_argument("-ts", "--test", dest="test_path", type=str, metavar='<str>', required=True, help="The path to the test set")
parser.add_argument("-o", "--out-dir", dest="out_dir_path", type=str, metavar='<str>', required=True, help="The path to the output directory")
parser.add_argument("-p", "--prompt", dest="prompt_id", type=int, metavar='<int>', required=False, help="Promp ID for ASAP dataset. '0' means all prompts.")
parser.add_argument("-t", "--type", dest="model_type", type=str, metavar='<str>', default='regp', help="Model type (reg|regp|breg|bregp) (default=regp)")
parser.add_argument("-u", "--rec-unit", dest="recurrent_unit", type=str, metavar='<str>', default='lstm', help="Recurrent unit type (lstm|gru|simple) (default=lstm)")
parser.add_argument("-a", "--algorithm", dest="algorithm", type=str, metavar='<str>', default='rmsprop', help="Optimization algorithm (rmsprop|sgd|adagrad|adadelta|adam|adamax) (default=rmsprop)")
parser.add_argument("-l", "--loss", dest="loss", type=str, metavar='<str>', default='mse', help="Loss function (mse|mae) (default=mse)")
parser.add_argument("-e", "--embdim", dest="emb_dim", type=int, metavar='<int>', default=50, help="Embeddings dimension (default=50)")
parser.add_argument("-c", "--cnndim", dest="cnn_dim", type=int, metavar='<int>', default=0, help="CNN output dimension. '0' means no CNN layer (default=0)")
parser.add_argument("-w", "--cnnwin", dest="cnn_window_size", type=int, metavar='<int>', default=3, help="CNN window size. (default=3)")
parser.add_argument("-r", "--rnndim", dest="rnn_dim", type=int, metavar='<int>', default=300, help="RNN dimension. '0' means no RNN layer (default=300)")
parser.add_argument("-b", "--batch-size", dest="batch_size", type=int, metavar='<int>', default=32, help="Batch size (default=32)")
parser.add_argument("-v", "--vocab-size", dest="vocab_size", type=int, metavar='<int>', default=4000, help="Vocab size (default=4000)")
parser.add_argument("--aggregation", dest="aggregation", type=str, metavar='<str>', default='mot', help="The aggregation method for regp and bregp types (mot|attsum|attmean) (default=mot)")
parser.add_argument("--dropout", dest="dropout_prob", type=float, metavar='<float>', default=0.5, help="The dropout probability. To disable, give a negative number (default=0.5)")
parser.add_argument("--vocab-path", dest="vocab_path", type=str, metavar='<str>', help="(Optional) The path to the existing vocab file (*.pkl)")
parser.add_argument("--skip-init-bias", dest="skip_init_bias", action='store_true', help="Skip initialization of the last layer bias")
parser.add_argument("--emb", dest="emb_path", type=str, metavar='<str>', help="The path to the word embeddings file (Word2Vec format)")
parser.add_argument("--epochs", dest="epochs", type=int, metavar='<int>', default=50, help="Number of epochs (default=50)")
parser.add_argument("--maxlen", dest="maxlen", type=int, metavar='<int>', default=5000, help="Maximum allowed number of words during training. '0' means no limit (default=0)")
parser.add_argument("--seed", dest="seed", type=int, metavar='<int>', default=1234, help="Random seed (default=1234)")
parser.add_argument("--clip_norm", dest="clip_norm", type=float, metavar='<float>', default=10.0, help="Threshold to clip gradients")
parser.add_argument("--pos", dest="pos", action='store_true', help="Use part of speech tagging in the training")
parser.add_argument("--variety", dest="variety", action='store_true', help="Variety of words in output layer")
parser.add_argument("--punct-count", dest="punct", action='store_true', help="Variety of words in output layer")
parser.add_argument('--cuda', dest='cuda', action='store_true', help='provide if you want to try using cuda')
args = parser.parse_args()

args.cuda = args.cuda and torch.cuda.is_available()

out_dir = args.out_dir_path.strip('\r\n')
model_save = os.path.join(out_dir,
                          'models/modelbgrepproper.pt')

U.mkdir_p(out_dir + '/preds')
U.mkdir_p(out_dir + '/models/')
U.mkdir_p(out_dir + '/logs/')

configure(os.path.join(out_dir,
                       'logs/'+args.nm),
          flush_secs=5)

U.set_logger(out_dir)
U.print_args(args)

DEFAULT_COMPRESSED_DATASET = 'datasets-pickled.pkl'


np.random.seed(args.seed)
torch.manual_seed(args.seed)
torch.cuda.manual_seed_all(args.seed)

if args.compressed_datasets == '':
    # train
    train_dataset = ASAPDataset(args.train_path, maxlen=args.maxlen, vocab_size=args.vocab_size, vocab_file=out_dir + '/vocab.pkl', pos=args.pos, read_vocab=(args.vocab_path is not None))
    vocab = train_dataset.vocab
    train_dataset.make_scores_model_friendly()
    # test
    test_dataset = ASAPDataset(args.test_path, maxlen=args.maxlen, vocab=vocab, pos=args.pos)
    test_dataset.make_scores_model_friendly()
    # dev
    dev_dataset = ASAPDataset(args.dev_path, maxlen=args.maxlen, vocab=vocab, pos=args.pos)
    dev_dataset.make_scores_model_friendly()

    max_seq_length = max(train_dataset.maxlen,
                         test_dataset.maxlen,
                         dev_dataset.maxlen)
    # Dump it!
    print('Dumping to', DEFAULT_COMPRESSED_DATASET)
    with open(DEFAULT_COMPRESSED_DATASET, 'wb') as f:
        stuff = {}
        stuff['train'] = train_dataset
        stuff['vocab'] = vocab
        stuff['test'] = test_dataset
        stuff['dev'] = dev_dataset
        stuff['msl'] = max_seq_length
        pk.dump(stuff, f)
else:
    with open(args.compressed_datasets, 'rb') as f:
        stuff = pk.load(f)
        train_dataset = stuff['train']
        vocab = stuff['vocab']
        test_dataset = stuff['test']
        dev_dataset = stuff['dev']
        max_seq_length = stuff['msl']


def mean0(ls):
    if isinstance(ls[0], list):
        islist = True
        mean = [0.0 for i in range(len(ls[0]))]
    else:
        islist = False
        mean = 0.0
    for i in range(len(ls)):
        if islist:
            for j in range(len(mean)):
                mean[j] += ls[i][j]
        else:
            mean += ls[i]
    if islist:
        for i in range(len(mean)):
            mean[i] /= len(ls)
    else:
        mean /= len(ls)
        mean = [mean]
    return mean


imv = mean0(train_dataset.y)
if args.ensemble_models is None:
    model = Model(args, vocab, imv)
else:
    model_name = args.ensemble_models
    model = EnsembleModel(model_name, args.ensemble_method)
if args.cuda:
    model.cuda()
    model = torch.nn.DataParallel(model)
    print('Model is on GPU')
torch.save(model, model_save)
optimizable_parameters = model.parameters()
loss_fn = F.mse_loss if args.loss == 'mse' else F.l1_loss
optimizer = U.get_optimizer(args, optimizable_parameters)

lcount = 0
model.train()
for epoch in range(args.epochs):
    losses = []
    batch_idx = -1
    # pdb.set_trace()
    loader = ASAPDataLoader(train_dataset, train_dataset.maxlen, args.batch_size)
    for xs, ys, ps, padding_mask, lens, (lhs, rhs) in loader:
        batch_idx += 1
        print('Starting batch %d' % batch_idx)
        if args.pos:
            indexes = train_dataset.tags_x[lhs:rhs]
        else:
            indexes = None
        if args.variety:
            variety = train_dataset.unique_x[lhs:rhs]
        else:
            variety = None
        if args.punct:
            punct = train_dataset.punct_x[lhs:rhs]
        else:
            punct = None
        if args.cuda:
            ys = ys.cuda()
        youts = model(xs,
                      mask=padding_mask,
                      lens=lens,
                      pos=indexes,
                      variety=variety,
                      punct=punct)
        loss = 0
        loss = loss_fn(youts, ys)
        losses.append(loss.data[0])
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm(optimizable_parameters, args.clip_norm)
        optimizer.step()
        print('\tloss=%f' % (losses[-1]))
        # logger.info(
        #     'Epoch=%d batch=%d loss=%f' % (epoch, batch_idx, losses[-1])
        #     )
        log_value('loss', loss.data[0], lcount)
        lcount += 1
    torch.save(model, model_save[:-3]+'.' + str(epoch)+'.pt')
    log_value('epoch_loss', sum(losses), epoch)
    print('Epoch %d: average loss=%f' % (epoch, sum(losses) / len(losses)))
torch.save(model, model_save)

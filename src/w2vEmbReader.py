import codecs
import logging
import numpy as np

logger = logging.getLogger(__name__)

class W2VEmbReader(object):
	"""
	
	"""
	def __init__(self, emb_path, emb_dim=None):
		logger.info('Loading embeddings from: ' + emb_path)
		has_header=False
		with codecs.open(emb_path, 'r', encoding='utf8') as emb_file:
			tokens = emb_file.next().split()
			if len(tokens) == 2:
				try:
					int(tokens[0])
					int(tokens[1])
					has_header = True
				except ValueError:
					pass
		if has_header:
			with codecs.open(emb_path, 'r', encoding='utf8') as emb_file:
				tokens = emb_file.next().split()
				assert len(tokens) == 2, 'The first line in W2V embeddings must be the pair (vocab_size, emb_dim)'
				self.vocab_size = int(tokens[0])
				self.emb_dim = int(tokens[1])
				assert self.emb_dim == emb_dim, 'The embeddings dimension does not match with the requested dimension'
				self.embeddings = {}
				counter = 0
				for line in emb_file:
					tokens = line.split()
					assert len(tokens) == self.emb_dim + 1, 'The number of dimensions does not match the header info'
					word = tokens[0]
					vec = tokens[1:]
					self.embeddings[word] = np.array(vec)
					counter += 1
				assert counter == self.vocab_size, 'Vocab size does not match the header info'
		else:
			with codecs.open(emb_path, 'r', encoding='utf8') as emb_file:
				self.vocab_size = 0
				self.emb_dim = -1
				self.embeddings = {}
				for line in emb_file:
					tokens = line.split()
					if self.emb_dim == -1:
						self.emb_dim = len(tokens) - 1
						assert self.emb_dim == emb_dim, 'The embeddings dimension does not match with the requested dimension'
					else:
						assert len(tokens) == self.emb_dim + 1, 'The number of dimensions does not match the header info'
					word = tokens[0]
					vec = tokens[1:]
					self.embeddings[word] = vec
					self.vocab_size += 1
		
		logger.info('  #vectors: %i, #dimensions: %i' % (self.vocab_size, self.emb_dim))
	
	def get_emb_given_word(self, word):
		try:
			return self.embeddings[word]
		except KeyError:
			return None
	
	def get_emb_matrix_given_vocab(self, vocab):
		counter = 0.
		ret = []
		for word, index in vocab.iteritems():
			embedding = self.get_emb_given_word(word)
			if embedding:
				ret.append(self.embeddings[word])
		logger.info('%i/%i word vectors initialized (hit rate: %.2f%%)' % 
			(len(embedding), len(vocab), (100.0 * len(embedding)) / len(vocab)))
		return np.array(ret)
	
	def get_emb_dim(self):
		return self.emb_dim
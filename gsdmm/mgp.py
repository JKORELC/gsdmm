"""
This module implements the Gibbs sampling algorithm for a Dirichlet Mixture Model (GSDMM)
of Yin and Wang 2014 for the clustering of short text documents.
"""

from typing import Any, Dict
from numpy.random import multinomial
from numpy import argmax, log, exp, array as np_array


TopicWords = Dict[Any, str]


class MovieGroupProcess:
    """
    This class implements the Gibbs sampling algorithm for a Dirichlet Mixture Model (GSDMM)
    of Yin and Wang 2014 for the clustering of short text documents.
    """

    # pylint: disable=invalid-name,too-many-instance-attributes
    def __init__(self, K=8, alpha=0.1, beta=0.1, n_iters=30):
        """
        A MovieGroupProcess is a conceptual model introduced by Yin and Wang 2014 to
        describe their Gibbs sampling algorithm for a Dirichlet Mixture Model for the
        clustering short text documents.
        Reference: http://dbgroup.cs.tsinghua.edu.cn/wangjy/papers/KDD14-GSDMM.pdf

        Imagine a professor is leading a film class. At the start of the class, the students
        are randomly assigned to K tables. Before class begins, the students make lists of
        their favorite films. The teacher reads the role n_iters times. When
        a student is called, the student must select a new table satisfying either:
            1) The new table has more students than the current table.
        OR
            2) The new table has students with similar lists of favorite movies.

        :param K: int
            Upper bound on the number of possible clusters. Typically many fewer
        :param alpha: float between 0 and 1
            Alpha controls the probability that a student will join a table that is currently empty
            When alpha is 0, no one will join an empty table.
        :param beta: float between 0 and 1
            Beta controls the student's affinity for other students with similar interests.
            A low beta means that students desire to sit with students of similar interests.
            A high beta means they are less concerned with affinity and are more influenced
            by the popularity of a table.
        :param n_iters:
            Number of iterations to resolve cluster definitions.
        """
        self.K = K  # pylint: disable=invalid-name
        self.alpha = alpha
        self.beta = beta
        self.n_iters = n_iters

        # slots for computed variables
        self.number_docs = None
        self.vocab_size = None
        self.cluster_doc_count = [0 for _ in range(K)]
        self.cluster_word_count = [0 for _ in range(K)]
        self.cluster_word_distribution = [{} for i in range(K)]

    # pylint: disable=invalid-name,too-many-arguments
    @staticmethod
    def from_data(
        K,
        alpha,
        beta,
        D,
        vocab_size,
        cluster_doc_count,
        cluster_word_count,
        cluster_word_distribution,
    ):
        """
        Reconstitute a MovieGroupProcess from previously fit data
        :param K:
        :param alpha:
        :param beta:
        :param D:
        :param vocab_size:
        :param cluster_doc_count:
        :param cluster_word_count:
        :param cluster_word_distribution:
        :return:
        """
        mgp = MovieGroupProcess(K, alpha, beta, n_iters=30)
        mgp.number_docs = D
        mgp.vocab_size = vocab_size
        mgp.cluster_doc_count = cluster_doc_count
        mgp.cluster_word_count = cluster_word_count
        mgp.cluster_word_distribution = cluster_word_distribution
        return mgp

    @staticmethod
    def _sample(p):
        """
        Sample with probability vector p from a multinomial distribution
        :param p: list
            List of probabilities representing probability vector for the multinomial distribution
        :return: int
            index of randomly selected output
        """
        return [i for i, entry in enumerate(multinomial(1, p)) if entry != 0][0]

    def fit(self, docs, vocab_size):
        """
        Cluster the input documents
        :param docs: list of list
            list of lists containing the unique token set of each document
        :param V: total vocabulary size for each document
        :return: list of length len(doc)
            cluster label for each document
        """
        # pylint: disable=invalid-name,too-many-locals
        _, __, K, n_iters, ___ = (
            self.alpha,
            self.beta,
            self.K,
            self.n_iters,
            vocab_size,
        )

        D = len(docs)
        self.number_docs = D
        self.vocab_size = vocab_size

        # unpack to easy var names
        m_z, n_z, n_z_w = (
            self.cluster_doc_count,
            self.cluster_word_count,
            self.cluster_word_distribution,
        )
        cluster_count = K
        d_z = [None for i in range(len(docs))]

        # initialize the clusters
        for i, doc in enumerate(docs):

            # choose a random  initial cluster for the doc
            z = self._sample([1.0 / K for _ in range(K)])
            d_z[i] = z
            m_z[z] += 1
            n_z[z] += len(doc)

            for word in doc:
                if word not in n_z_w[z]:
                    n_z_w[z][word] = 0
                n_z_w[z][word] += 1

        for _iter in range(n_iters):
            total_transfers = 0

            for i, doc in enumerate(docs):

                # remove the doc from it's current cluster
                z_old = d_z[i]

                m_z[z_old] -= 1
                n_z[z_old] -= len(doc)

                for word in doc:
                    n_z_w[z_old][word] -= 1

                    # compact dictionary to save space
                    if n_z_w[z_old][word] == 0:
                        del n_z_w[z_old][word]

                # draw sample from distribution to find new cluster
                p = self.score(doc)
                z_new = self._sample(p)

                # transfer doc to the new cluster
                if z_new != z_old:
                    total_transfers += 1

                d_z[i] = z_new
                m_z[z_new] += 1
                n_z[z_new] += len(doc)

                for word in doc:
                    if word not in n_z_w[z_new]:
                        n_z_w[z_new][word] = 0
                    n_z_w[z_new][word] += 1

            cluster_count_new = sum(v > 0 for v in m_z)
            print(
                f"In stage {_iter}: transferred {total_transfers} clusters "
                f"with {cluster_count_new} clusters populated"
            )
            if (
                total_transfers == 0
                and cluster_count_new == cluster_count
                and _iter > 25
            ):
                print("Converged.  Breaking out.")
                break
            cluster_count = cluster_count_new
        self.cluster_word_distribution = n_z_w
        return d_z

    def score(self, doc):  # pylint: disable=too-many-locals
        """
        Score a document

        Implements formula (3) of Yin and Wang 2014.
        http://dbgroup.cs.tsinghua.edu.cn/wangjy/papers/KDD14-GSDMM.pdf

        :param doc: list[str]: The doc token stream
        :return: list[float]: A length K probability vector where each component represents
                              the probability of the document appearing in a particular cluster
        """
        # pylint: disable=invalid-name
        alpha, beta, K, V, D = (
            self.alpha,
            self.beta,
            self.K,
            self.vocab_size,
            self.number_docs,
        )
        m_z, n_z, n_z_w = (
            self.cluster_doc_count,
            self.cluster_word_count,
            self.cluster_word_distribution,
        )

        p = [0 for _ in range(K)]

        #  We break the formula into the following pieces
        #  p = N1*N2/(D1*D2) = exp(lN1 - lD1 + lN2 - lD2)
        #  lN1 = log(m_z[z] + alpha)
        #  lN2 = log(D - 1 + K*alpha)
        #  lN2 = log(product(n_z_w[w] + beta)) = sum(log(n_z_w[w] + beta))
        #  lD2 = log(product(n_z[d] + V*beta + i -1)) = sum(log(n_z[d] + V*beta + i -1))

        lD1 = log(D - 1 + K * alpha)
        doc_size = len(doc)
        for label in range(K):
            lN1 = log(m_z[label] + alpha)
            lN2 = 0
            lD2 = 0
            for word in doc:
                lN2 += log(n_z_w[label].get(word, 0) + beta)
            for j in range(1, doc_size + 1):
                lD2 += log(n_z[label] + V * beta + j - 1)
            p[label] = exp(lN1 - lD1 + lN2 - lD2)

        # normalize the probability vector
        pnorm = sum(p)
        pnorm = pnorm if pnorm > 0 else 1
        return [pp / pnorm for pp in p]

    def choose_best_label(self, doc):
        """
        Choose the highest probability label for the input document
        :param doc: list[str]: The doc token stream
        :return:
        """
        p = self.score(doc)
        return argmax(p), max(p)

    def get_top_words(self, k_words: int = 5, merge_token: str = " ") -> TopicWords:
        """
        Filter the top k_words entries per cluster using merge_token as a separator.
        """
        doc_count = np_array(self.cluster_doc_count)
        top_index = doc_count.argsort()[-self.K :][::-1]
        topic_words: TopicWords = {}

        for cluster in top_index:
            items = self.cluster_word_distribution[cluster].items()
            sort_dicts = sorted(items, key=lambda k: k[1], reverse=True)[:k_words]
            words = merge_token.join([wc[0] for wc in sort_dicts])
            topic_words[int(cluster)] = words

        return topic_words

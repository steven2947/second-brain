"""中文关键词基线、本地向量与 RRF 混合检索；排序分数不表示事实可信度。"""

import hashlib
import math
import re
import os
import tempfile
import zipfile
from importlib.metadata import version as package_version
from collections import Counter
from pathlib import Path


def tokenize(text):
    """text 为待检索文字；中文采用相邻双字及英文词，不依赖外部服务。"""
    words = re.findall(r'[a-z0-9]+', text.lower())
    for run in re.findall(r'[\u4e00-\u9fff]+', text):
        words.extend(run[i:i+2] for i in range(max(0, len(run)-1)))
    stop = {'什么', '怎么', '如何', '我的', '这个', '一个', '这本', '本书', '我想', '可以', '哪些', '告诉', '根据'}
    return [word for word in words if word not in stop]


def fuse_rankings(rankings):
    """合并有序 ID 列表 rankings；每个通道每个 ID 最多计算一次。"""
    scores = Counter()
    for ranking in rankings:
        seen = set()
        for rank, identifier in enumerate(ranking, 1):
            if identifier not in seen:
                scores[identifier] += 1 / (60 + rank)
                seen.add(identifier)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


def card_text(card):
    """构造卡片检索文本；card 为已验收记录，保持短文本以免模型截断核心观点。"""
    fields = [card['title'], card['statement'], ' '.join(card.get('keywords', [])),
              ' '.join(card.get('trigger_questions', [])), ' '.join(card.get('conditions', []))]
    return '\n'.join(fields)[:1600]


class SearchEngine:
    """为固定知识版本提供三种检索方式。"""

    def __init__(self, library, index_root=None, model_cache=None):
        """library 为只读 Library；index_root/model_cache 为可重建的本地缓存路径。"""
        self.library = library
        self.ids = sorted(library.cards)
        self.texts = [card_text(library.cards[key]) for key in self.ids]
        self.counts = [Counter(tokenize(text)) for text in self.texts]
        self.df = Counter(term for counter in self.counts for term in counter)
        self.avg_length = sum(sum(c.values()) for c in self.counts) / max(1, len(self.counts))
        self.index_root = Path(index_root) if index_root else None
        self.model_cache = str(model_cache) if model_cache else None
        self.model_name = 'BAAI/bge-small-zh-v1.5'
        self.model = None
        self.vectors = None

    def keyword_scores(self, query):
        """为 query 计算 BM25，零匹配保持 0 分。"""
        tokens = set(tokenize(query)); result = {}
        for identifier, terms in zip(self.ids, self.counts):
            length = sum(terms.values()); score = 0
            for term in tokens:
                tf = terms[term]
                if tf:
                    idf = math.log(1 + (len(self.ids)-self.df[term]+0.5)/(self.df[term]+0.5))
                    score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length/max(1, self.avg_length)))
            result[identifier] = score
        return result

    def load_vectors(self):
        """建立或读取当前版本向量；模型在本地 CPU 执行，首次使用只下载模型文件。"""
        import numpy as np
        from fastembed import TextEmbedding
        if self.model is None:
            self.model = TextEmbedding(model_name=self.model_name, cache_dir=self.model_cache, threads=2)
        if self.vectors is not None:
            return
        digest = hashlib.sha256((self.model_name+'\0'+package_version('fastembed')+'\0'+'\0'.join(self.texts)).encode())
        model_dir = getattr(getattr(self.model,'model',None),'_model_dir',None)
        if isinstance(model_dir,(str,Path)):
            for file in sorted(Path(model_dir).rglob('*')):
                if file.is_file():
                    digest.update(file.relative_to(model_dir).as_posix().encode())
                    digest.update(hashlib.sha256(file.read_bytes()).digest())
        signature = digest.hexdigest()
        path = self.index_root / self.library.version / 'vectors.npz' if self.index_root else None
        if path and path.is_file():
            try:
                with np.load(path, allow_pickle=False) as saved:
                    vectors = saved['vectors']
                    expected_dim = getattr(self.model,'embedding_size',None)
                    valid_dim = not isinstance(expected_dim,int) or vectors.shape[-1:] == (expected_dim,)
                    if (str(saved['signature']) == signature and saved['ids'].tolist() == self.ids
                        and vectors.ndim == 2 and vectors.shape[0] == len(self.ids)
                        and valid_dim and np.isfinite(vectors).all()):
                        self.vectors = vectors
            except (OSError,ValueError,KeyError,EOFError,zipfile.BadZipFile):
                # 缓存损坏只触发重建，不允许 pickle，也不修改知识事实源。
                pass
            if self.vectors is not None:
                return
        vectors = np.asarray(list(self.model.passage_embed(self.texts, batch_size=16)), dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        self.vectors = vectors / np.maximum(norms, 1e-12)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix='.vectors-', suffix='.npz', dir=path.parent)
            os.close(descriptor)
            try:
                np.savez_compressed(temporary, vectors=self.vectors, ids=np.array(self.ids), signature=signature)
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)

    def semantic_scores(self, query):
        """query 为原始或扩展问题；返回与文档向量的余弦相似度。"""
        import numpy as np
        self.load_vectors()
        vector = np.asarray(next(iter(self.model.query_embed(query))), dtype=np.float32)
        vector /= max(float(np.linalg.norm(vector)), 1e-12)
        return dict(zip(self.ids, (self.vectors @ vector).tolist()))

    def search(self, query, mode='hybrid', book=None, author=None, limit=5, expansions=None, min_similarity=0.45):
        """检索 query；mode 选 keyword/semantic/hybrid，过滤器按书籍或作者 ID/名称，expansions 为补充问法。"""
        if not isinstance(query, str) or not query.strip() or len(query) > 4000:
            raise ValueError('INVALID_ARGUMENT: 问题为空或过长')
        if mode not in ('keyword', 'semantic', 'hybrid') or type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError('INVALID_ARGUMENT: 检索模式或条数无效')
        if not 0 <= min_similarity <= 1 or len(expansions or []) > 5:
            raise ValueError('INVALID_ARGUMENT: 阈值或扩展问法无效')
        books = {b['id']: b for b in self.library.manifest['books']}
        eligible = {key for key in self.ids if
                    (not book or book in (self.library.cards[key]['book_id'], books[self.library.cards[key]['book_id']]['title'])) and
                    (not author or author in (self.library.cards[key]['author_id'], books[self.library.cards[key]['book_id']].get('author')))}
        if not eligible:
            return []
        queries = [query] + list(expansions or [])
        rankings, keyword, semantic = [], {}, {}
        for text in queries:
            if not isinstance(text, str) or len(text) > 4000:
                raise ValueError('INVALID_ARGUMENT: 扩展问法无效')
            if mode in ('keyword', 'hybrid'):
                scores = self.keyword_scores(text)
                for key, score in scores.items(): keyword[key] = max(keyword.get(key, 0), score)
                rankings.append([key for key in sorted(eligible, key=lambda k: (-scores[k], k)) if scores[key] > 0][:50])
            if mode in ('semantic', 'hybrid'):
                scores = self.semantic_scores(text)
                for key, score in scores.items(): semantic[key] = max(semantic.get(key, -1), score)
                rankings.append([key for key in sorted(eligible, key=lambda k: (-scores[k], k)) if scores[key] >= min_similarity][:50])
        results = []
        fused = fuse_rankings(rankings)
        if mode == 'hybrid':
            # 常见词命中不够作为推荐依据；保留原问题或扩展问法中达到相关性门槛的卡片。
            fused = [(key,score) for key,score in fused if semantic.get(key,-1) >= min_similarity]
        for key, score in fused[:limit]:
            results.append({'card': self.library.cards[key], 'score': score, 'score_kind': 'rrf_not_confidence',
                            'keyword_score': keyword.get(key), 'semantic_similarity': semantic.get(key),
                            'mode': mode, 'book': books[self.library.cards[key]['book_id']]})
        return results

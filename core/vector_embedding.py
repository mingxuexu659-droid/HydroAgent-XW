#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向量嵌入模块 - 使用百炼API进行文本向量化

提供 VectorEmbeddingClient 类，用于将文本转换为向量表示
"""

import os
import sys
import requests
from typing import List, Optional

# Add the project root so optional local settings can be resolved.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DASHSCOPE_API_KEY

# 百炼API配置
DASHSCOPE_EMBEDDING_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
DASHSCOPE_EMBEDDING_MODEL = "text-embedding-v2"


class VectorEmbeddingClient:
    """百炼API向量化客户端"""
    
    def __init__(self, api_key: str = None, api_url: str = None, model_name: str = None, timeout: float = None):
        """
        初始化向量嵌入客户端
        
        Args:
            api_key: 百炼API密钥，默认使用 DASHSCOPE_API_KEY
            api_url: API地址，默认使用 DASHSCOPE_EMBEDDING_API_URL
            model_name: 模型名称，默认使用 DASHSCOPE_EMBEDDING_MODEL
            timeout: 请求超时时间（秒），默认10秒
        """
        self.api_key = api_key or DASHSCOPE_API_KEY
        self.api_url = api_url or DASHSCOPE_EMBEDDING_API_URL
        self.model_name = model_name or DASHSCOPE_EMBEDDING_MODEL
        self.timeout = timeout if timeout is not None else 10.0
    
    def embed_text(self, text: str) -> Optional[List[float]]:
        """
        将文本转换为向量
        
        Args:
            text: 待向量化的文本
            
        Returns:
            向量列表，如果失败返回None
        """
        if not text or not text.strip():
            return None
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 百炼API格式：input必须是对象，包含texts数组
        payload = {
            "model": self.model_name,
            "input": {
                "texts": [text]
            }
        }
        
        try:
            response = requests.post(self.api_url, json=payload, headers=headers, timeout=self.timeout)
            if response.status_code == 200:
                result = response.json()
                # 百炼API响应格式: {"output": {"embeddings": [{"embedding": [...]}]}}
                if 'output' in result and 'embeddings' in result['output']:
                    embeddings = result['output']['embeddings']
                    if embeddings and len(embeddings) > 0:
                        if isinstance(embeddings[0], dict) and 'embedding' in embeddings[0]:
                            return embeddings[0]['embedding']
            else:
                print(f"⚠️ 向量化API调用失败: {response.status_code} - {response.text[:200]}")
        except Exception as e:
            print(f"⚠️ 向量化异常: {e}")
        
        return None
    
    def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        批量向量化文本
        
        Args:
            texts: 待向量化的文本列表
            
        Returns:
            向量列表，每个元素对应一个文本的向量（失败则为None）
        """
        if not texts:
            return []
        
        # 批量向量化：逐个处理（百炼API可能不支持批量，或格式不同）
        # 为了简化，这里逐个调用
        results = []
        for text in texts:
            vector = self.embed_text(text)
            results.append(vector)
        
        return results


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    计算两个向量的余弦相似度
    
    Args:
        vec1: 第一个向量
        vec2: 第二个向量
        
    Returns:
        余弦相似度值（0-1之间）
    """
    import math
    
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(a * a for a in vec2))
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    return dot_product / (magnitude1 * magnitude2)


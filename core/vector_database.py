#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向量数据库 - 用于存储和检索数据集的向量表示

向量数据库存储格式：
{
    "metadata": {
        "version": "1.0.0",
        "created_at": "2025-01-09T...",
        "updated_at": "2025-01-09T...",
        "total_vectors": 0
    },
    "vectors": [
        {
            "dataset_id": "unique_id",  # 对应catalog中的数据集ID或文件路径
            "description": "数据集的description字段",
            "vector": [0.123, -0.456, ...],  # 向量表示
            "created_at": "2025-01-09T..."
        }
    ]
}
"""

import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


class VectorDatabase:
    """向量数据库"""
    
    def __init__(self, db_path: str):
        """
        初始化向量数据库
        
        Args:
            db_path: 向量数据库文件路径（JSON格式）
        """
        self.db_path = Path(db_path)
        self.db_data = self._load_database()
    
    def _load_database(self) -> Dict[str, Any]:
        """加载向量数据库"""
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Failed to load vector database: {e}, creating new database")
        
        # 创建新的数据库结构
        return {
            "metadata": {
                "version": "1.0.0",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "total_vectors": 0
            },
            "vectors": []
        }
    
    def _save_database(self):
        """保存向量数据库"""
        self.db_data["metadata"]["updated_at"] = datetime.now().isoformat()
        self.db_data["metadata"]["total_vectors"] = len(self.db_data["vectors"])
        
        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(self.db_data, f, ensure_ascii=False, indent=2)
    
    def _generate_dataset_id(self, file_path: str) -> str:
        """
        生成数据集ID（基于文件路径的哈希值）
        
        Args:
            file_path: 文件绝对路径
            
        Returns:
            数据集ID
        """
        return hashlib.md5(file_path.encode('utf-8')).hexdigest()
    
    def add_vector(self, dataset_id: str, description: str, vector: List[float]) -> bool:
        """
        添加向量到数据库
        
        Args:
            dataset_id: 数据集ID（文件路径的哈希值）
            description: 数据集的description字段
            vector: 向量表示
            
        Returns:
            是否成功添加
        """
        if not vector or len(vector) == 0:
            return False
        
        # 检查是否已存在
        existing_idx = None
        for idx, vec_item in enumerate(self.db_data["vectors"]):
            if vec_item["dataset_id"] == dataset_id:
                existing_idx = idx
                break
        
        vector_item = {
            "dataset_id": dataset_id,
            "description": description,
            "vector": vector,
            "created_at": datetime.now().isoformat()
        }
        
        if existing_idx is not None:
            # 更新现有向量
            self.db_data["vectors"][existing_idx] = vector_item
            print(f"   Update vector: {dataset_id}")
        else:
            # 添加新向量
            self.db_data["vectors"].append(vector_item)
            print(f"   Added vector: {dataset_id}")
        
        self._save_database()
        return True
    
    def get_vector(self, dataset_id: str) -> Optional[List[float]]:
        """
        获取指定数据集的向量
        
        Args:
            dataset_id: 数据集ID
            
        Returns:
            向量表示，如果不存在返回None
        """
        for vec_item in self.db_data["vectors"]:
            if vec_item["dataset_id"] == dataset_id:
                return vec_item["vector"]
        return None
    
    def get_all_vectors(self) -> List[Dict[str, Any]]:
        """
        获取所有向量
        
        Returns:
            向量列表，每个包含 dataset_id, description, vector
        """
        return self.db_data["vectors"].copy()
    
    def remove_vector(self, dataset_id: str) -> bool:
        """
        删除指定数据集的向量
        
        Args:
            dataset_id: 数据集ID
            
        Returns:
            是否成功删除
        """
        for idx, vec_item in enumerate(self.db_data["vectors"]):
            if vec_item["dataset_id"] == dataset_id:
                del self.db_data["vectors"][idx]
                self._save_database()
                return True
        return False
    
    def clear(self):
        """清空向量数据库"""
        self.db_data["vectors"] = []
        self._save_database()
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        return {
            "total_vectors": len(self.db_data["vectors"]),
            "created_at": self.db_data["metadata"]["created_at"],
            "updated_at": self.db_data["metadata"]["updated_at"]
        }


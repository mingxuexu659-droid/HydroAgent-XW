# -*- coding: utf-8 -*-
"""
LLM客户端模块

提供与大语言模型交互的客户端，支持OpenAI兼容的API。
"""

import json
from typing import Any, Dict, List, Optional, Tuple
from openai import OpenAI

from .config import Config, LLMConfig, get_config


class LLMClient:
    """
    LLM客户端
    
    支持OpenAI兼容的API，用于意图分析、代码生成和代码优化。
    """
    
    def __init__(self, config: Optional[Config] = None, llm_config_override: Optional[LLMConfig] = None):
        """
        初始化LLM客户端
        
        Args:
            config: 配置对象，如果为None则使用全局配置
            llm_config_override: LLM配置覆盖，用于使用不同的模型（如代码生成专用模型）
        """
        self.config = config or get_config()
        
        # 使用覆盖配置或默认配置
        llm_cfg = llm_config_override or self.config.llm
        
        api_key = llm_cfg.api_key
        if not api_key:
            raise ValueError("LLM API Key未配置，请在config.yaml中设置api_key或设置环境变量AUTOGIS_API_KEY")
        
        # 创建OpenAI客户端，设置超时
        import httpx
        # 设置超时：连接超时10秒，总超时使用配置值
        timeout = httpx.Timeout(llm_cfg.timeout, connect=10.0)
        self.client = OpenAI(
            api_key=api_key,
            base_url=llm_cfg.base_url,
            timeout=timeout
        )
        self.model = llm_cfg.model_name
        self.default_temperature = llm_cfg.temperature
        self.max_tokens = llm_cfg.max_tokens
        self.timeout = llm_cfg.timeout
        
        # 记录使用的模型信息
        self._model_info = f"{llm_cfg.model_name} @ {llm_cfg.base_url}"
    
    def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False
    ) -> Tuple[Optional[str], Dict[str, int]]:
        """
        发送聊天请求
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            temperature: 温度参数
            max_tokens: 最大token数
            json_mode: 是否启用JSON输出模式
        
        Returns:
            (response_text, token_stats): 响应文本和token统计
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature if temperature is not None else self.default_temperature,
            }
            
            if max_tokens:
                kwargs["max_tokens"] = max_tokens
            
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            
            response = self.client.chat.completions.create(**kwargs)
            
            response_text = response.choices[0].message.content
            
            # 获取token统计
            token_stats = {
                "input_tokens": getattr(response.usage, 'prompt_tokens', 0),
                "output_tokens": getattr(response.usage, 'completion_tokens', 0),
                "total_tokens": getattr(response.usage, 'total_tokens', 0)
            }
            
            return response_text, token_stats
            
        except Exception as e:
            print(f"❌ LLM call failed: {e}")
            return None, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    
    def chat_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, int]]:
        """
        发送聊天请求并解析JSON响应
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            temperature: 温度参数
        
        Returns:
            (json_data, token_stats): 解析后的JSON数据和token统计
        """
        response_text, token_stats = self.chat(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            json_mode=True
        )
        
        if response_text is None:
            return None, token_stats
        
        try:
            # 尝试解析JSON
            json_data = json.loads(response_text)
            return json_data, token_stats
        except json.JSONDecodeError:
            # 如果直接解析失败，尝试提取JSON块
            json_data = self._extract_json_from_text(response_text)
            return json_data, token_stats
    
    def _extract_json_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """
        从文本中提取JSON
        
        Args:
            text: 包含JSON的文本
        
        Returns:
            解析后的JSON数据，如果提取失败则返回None
        """
        import re
        
        # 尝试从markdown代码块中提取
        json_block_pattern = r'```(?:json)?\s*\n?([\s\S]*?)\n?```'
        matches = re.findall(json_block_pattern, text)
        
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue
        
        # 尝试直接查找JSON对象
        brace_start = text.find('{')
        brace_end = text.rfind('}')
        
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                pass
        
        return None
    
    def extract_code_from_response(self, response: str) -> Optional[str]:
        """
        从LLM响应中提取Python代码
        
        Args:
            response: LLM响应文本
        
        Returns:
            提取的Python代码，如果提取失败则返回None
        """
        import re
        
        # 尝试从python代码块中提取
        python_block_pattern = r'```python\s*\n([\s\S]*?)\n```'
        matches = re.findall(python_block_pattern, response)
        
        if matches:
            # 返回最长的代码块（通常是主要代码）
            return max(matches, key=len).strip()
        
        # 尝试从普通代码块中提取
        code_block_pattern = r'```\s*\n([\s\S]*?)\n```'
        matches = re.findall(code_block_pattern, response)
        
        if matches:
            # 检查是否像Python代码
            for match in matches:
                if 'import ' in match or 'def ' in match or 'processing.run' in match:
                    return match.strip()
        
        # 如果没有代码块，检查整个响应是否是代码
        if 'import ' in response and ('processing.run' in response or 'QgsProject' in response):
            # 移除可能的解释文字
            lines = response.split('\n')
            code_lines = []
            in_code = False
            
            for line in lines:
                stripped = line.strip()
                # 跳过开头的解释文字
                if not in_code:
                    if stripped.startswith(('import ', 'from ', '#', 'def ', 'class ')):
                        in_code = True
                        code_lines.append(line)
                else:
                    code_lines.append(line)
            
            if code_lines:
                return '\n'.join(code_lines).strip()
        
        return None


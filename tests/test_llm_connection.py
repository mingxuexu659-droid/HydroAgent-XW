# -*- coding: utf-8 -*-
"""
LLM 连接诊断测试

用于诊断 LLM 调用超时问题
"""

import os
import sys
import time
import pytest

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# These are manual diagnostics that can incur provider charges and require
# network access. They stay out of the default test suite.
pytestmark = pytest.mark.skipif(
    os.environ.get("AUTOGIS_RUN_NETWORK_TESTS", "").lower() != "true",
    reason="set AUTOGIS_RUN_NETWORK_TESTS=true to run live LLM diagnostics",
)


def test_basic_network():
    """测试基本网络连接"""
    import requests
    
    print("\n" + "="*60)
    print("🔍 测试1: 基本网络连接")
    print("="*60)
    
    test_urls = [
        ("https://www.baidu.com", "百度"),
        ("https://dashscope.aliyuncs.com", "阿里云DashScope"),
    ]
    
    for url, name in test_urls:
        try:
            start = time.time()
            resp = requests.get(url, timeout=10)
            elapsed = time.time() - start
            print(f"  ✅ {name}: 状态码={resp.status_code}, 耗时={elapsed:.2f}秒")
        except requests.exceptions.Timeout:
            print(f"  ❌ {name}: 连接超时")
        except requests.exceptions.ConnectionError as e:
            print(f"  ❌ {name}: 连接错误 - {e}")
        except Exception as e:
            print(f"  ❌ {name}: 未知错误 - {type(e).__name__}: {e}")


def test_openai_client_direct():
    """直接测试 OpenAI 客户端"""
    from openai import OpenAI
    import httpx
    
    print("\n" + "="*60)
    print("🔍 测试2: 直接调用 OpenAI 客户端")
    print("="*60)
    
    api_key = os.environ.get("AUTOGIS_API_KEY", "")
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model = "qwen-max"
    
    print(f"  API key configured: {bool(api_key)}")
    print(f"  Base URL: {base_url}")
    print(f"  Model: {model}")
    
    # 设置不同的超时时间测试
    timeouts = [30, 60, 120]
    
    for timeout_sec in timeouts:
        print(f"\n  📡 测试超时时间: {timeout_sec}秒...")
        try:
            timeout = httpx.Timeout(timeout_sec, connect=10.0)
            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout
            )
            
            start = time.time()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": "请回复'测试成功'两个字"}
                ],
                temperature=0.1,
                max_tokens=50
            )
            elapsed = time.time() - start
            
            content = response.choices[0].message.content
            print(f"  ✅ 成功! 耗时={elapsed:.2f}秒")
            print(f"     响应: {content[:100]}")
            print(f"     Token使用: 输入={response.usage.prompt_tokens}, 输出={response.usage.completion_tokens}")
            return True  # 成功则退出
            
        except httpx.TimeoutException as e:
            elapsed = time.time() - start
            print(f"  ❌ 超时 ({elapsed:.2f}秒): {type(e).__name__}")
        except httpx.ConnectError as e:
            print(f"  ❌ 连接错误: {e}")
        except Exception as e:
            elapsed = time.time() - start
            print(f"  ❌ 错误 ({elapsed:.2f}秒): {type(e).__name__}: {e}")
    
    return False


def test_with_proxy():
    """测试使用代理"""
    from openai import OpenAI
    import httpx
    
    print("\n" + "="*60)
    print("🔍 测试3: 使用代理连接")
    print("="*60)
    
    api_key = os.environ.get("AUTOGIS_API_KEY", "")
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model = "qwen-max"
    proxy = os.environ.get("AUTOGIS_PROXY_URL", "")
    
    print(f"  代理: {proxy}")
    
    try:
        # 创建带代理的 httpx 客户端
        http_client = httpx.Client(
            proxies=proxy,
            timeout=httpx.Timeout(60.0, connect=10.0)
        )
        
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client
        )
        
        start = time.time()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": "请回复'代理测试成功'"}
            ],
            temperature=0.1,
            max_tokens=50
        )
        elapsed = time.time() - start
        
        content = response.choices[0].message.content
        print(f"  ✅ 代理连接成功! 耗时={elapsed:.2f}秒")
        print(f"     响应: {content[:100]}")
        return True
        
    except Exception as e:
        print(f"  ❌ 代理连接失败: {type(e).__name__}: {e}")
        return False


def test_llm_client_module():
    """测试 LLMClient 模块"""
    print("\n" + "="*60)
    print("🔍 测试4: 测试 LLMClient 模块")
    print("="*60)
    
    try:
        from spatial_analysis_system.llm_client import LLMClient
        from spatial_analysis_system.config import get_config
        
        config = get_config()
        print(f"  配置文件: {config.config_path}")
        print(f"  API key configured: {bool(config.llm.api_key)}")
        print(f"  Base URL: {config.llm.base_url}")
        print(f"  Model: {config.llm.model_name}")
        print(f"  Timeout: {config.llm.timeout}秒")
        
        client = LLMClient(config)
        print(f"  ✅ LLMClient 初始化成功")
        
        print(f"\n  📡 发送测试请求...")
        start = time.time()
        response, stats = client.chat(
            prompt="请回复'模块测试成功'",
            temperature=0.1
        )
        elapsed = time.time() - start
        
        if response:
            print(f"  ✅ 请求成功! 耗时={elapsed:.2f}秒")
            print(f"     响应: {response[:100]}")
            print(f"     Token使用: 输入={stats['input_tokens']}, 输出={stats['output_tokens']}")
            return True
        else:
            print(f"  ❌ 请求失败 (返回None)")
            return False
            
    except Exception as e:
        import traceback
        print(f"  ❌ 错误: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False


def test_dns_resolution():
    """测试 DNS 解析"""
    import socket
    
    print("\n" + "="*60)
    print("🔍 测试5: DNS 解析")
    print("="*60)
    
    hosts = [
        "dashscope.aliyuncs.com",
        "www.baidu.com",
    ]
    
    for host in hosts:
        try:
            start = time.time()
            ip = socket.gethostbyname(host)
            elapsed = time.time() - start
            print(f"  ✅ {host} -> {ip} (耗时={elapsed:.3f}秒)")
        except socket.gaierror as e:
            print(f"  ❌ {host}: DNS解析失败 - {e}")


def main():
    print("\n" + "="*60)
    print("🔬 LLM 连接诊断测试")
    print("="*60)
    
    # 测试顺序：从简单到复杂
    test_dns_resolution()
    test_basic_network()
    
    success = test_openai_client_direct()
    
    if not success:
        print("\n⚠️ 直接连接失败，尝试代理连接...")
        test_with_proxy()
    
    test_llm_client_module()
    
    print("\n" + "="*60)
    print("📋 诊断完成")
    print("="*60)
    print("""
如果测试失败，请检查：
1. 网络连接是否正常
2. API Key 是否有效
3. 是否需要使用代理
4. 阿里云 DashScope 服务是否正常

如果需要使用代理，请在 config.yaml 中添加代理配置或设置环境变量:
  export HTTP_PROXY=http://127.0.0.1:7897
  export HTTPS_PROXY=http://127.0.0.1:7897
""")


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试数据转换模块"""
from src.convert import convert_to_jsonlines, stream_jsonlines, batch_convert
from pathlib import Path

def test_standardize_item():
    """测试字段标准化的函数"""
    
    # 正常情况
    item = {
        "评论 ID": "123",
        "产品": "游戏 A",
        "情绪": "positive",
        "score": "4.5",
    }
    result = convert_to_jsonlines([item], "test_output.jsonl")
    assert result == 1
    
    # 缺失字段
    item_partial = {"产品": "游戏 B"}
    result = convert_to_jsonlines([item_partial], "test_output.jsonl")
    assert result == 1
    
    print("✓ test_standardize_item 通过")

def test_stream_jsonlines():
    """测试流式转换"""
    
    items = [
        {"comment_id": "1", "product": "A", "sentiment": "positive"},
        {"comment_id": "2", "product": "A", "sentiment": "negative"},
    ]
    result = stream_jsonlines(items)
    assert result["items_written"] == 2
    print("✓ test_stream_jsonlines 通过")

def test_batch_convert():
    """测试批量转换"""
    
    # 创建测试文件
    with open("test_input1.jsonl", "w") as f:
        f.write('{"comment_id": "1", "product": "A", "sentiment": "positive"}\n')
    
    with open("test_input2.jsonl", "w") as f:
        f.write('{"comment_id": "2", "product": "A", "sentiment": "negative"}\n')
    
    result = batch_convert("test_input*.jsonl", "test_output.jsonl")
    assert result["items_written"] == 2
    assert result["input_files"] == 2
    
    # 清理
    for f in ["test_input1.jsonl", "test_input2.jsonl", "test_output.jsonl"]:
        try:
            Path(f).unlink()
        except FileNotFoundError:
            pass
    
    print("✓ test_batch_convert 通过")

if __name__ == "__main__":
    test_standardize_item()
    test_stream_jsonlines()
    test_batch_convert()
    print("\n所有单元测试通过！")
